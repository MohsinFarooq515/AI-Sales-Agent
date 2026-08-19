from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.models import (CrmLeadUpdate, EventRequest, HumanReplyRequest, InquiryRequest,
                            IntegrationLeadUpdate)
from app.agent.lead_scoring import calculate_lead_score
from app.agent.models import LeadProfile
from app.agent.sales_stage import determine_sales_stage
from app.core.config import settings
from app.db.database import get_db
from app.db.models import (AnalyticsEventDB, ConversationDB, CrmLeadStateDB, IntegrationSettingDB,
                           IntegrationDeliveryDB, LeadDB, MessageDB)
from app.db.repository import add_analytics_event, add_message, get_lead_profile, save_lead_profile
from app.integrations.webhooks import sync_lead_background
from app.integrations.email_notifications import send_visitor_reply


router = APIRouter(prefix="/api", tags=["Analytics"])


def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.get("/admin/auth", dependencies=[Depends(require_admin)])
def verify_admin_key():
    """Validate dashboard access without returning protected data."""
    return {"authenticated": True}


@router.delete("/admin/demo-data", dependencies=[Depends(require_admin)])
def clear_demo_data(confirm: str, db: Session = Depends(get_db)):
    """Clear visitor and sales activity while preserving knowledge and integrations."""
    if confirm != "RESET_DEMO_DATA":
        raise HTTPException(status_code=400, detail="Reset confirmation is incorrect")

    counts = {
        "conversations": db.scalar(select(func.count()).select_from(ConversationDB)) or 0,
        "messages": db.scalar(select(func.count()).select_from(MessageDB)) or 0,
        "leads": db.scalar(select(func.count()).select_from(LeadDB)) or 0,
        "analytics_events": db.scalar(select(func.count()).select_from(AnalyticsEventDB)) or 0,
        "integration_deliveries": db.scalar(
            select(func.count()).select_from(IntegrationDeliveryDB)
        ) or 0,
        "crm_lead_states": db.scalar(select(func.count()).select_from(CrmLeadStateDB)) or 0,
    }

    # Delete dependants before conversations. Knowledge embeddings, OAuth credentials,
    # and integration/knowledge-refresh settings intentionally remain untouched.
    for model in (
        CrmLeadStateDB,
        IntegrationDeliveryDB,
        AnalyticsEventDB,
        MessageDB,
        LeadDB,
        ConversationDB,
    ):
        db.execute(delete(model))
    db.commit()
    return {"cleared": True, "deleted": counts}


@router.post("/events", status_code=202)
def track_event(request: EventRequest, db: Session = Depends(get_db)):
    add_analytics_event(db, request.event_type, request.session_id, request.data)
    return {"accepted": True}


@router.get("/config")
def public_config():
    return {"calendly_url": settings.calendly_url, "company_phone": settings.company_phone}


@router.post("/integrations/calendar", status_code=202)
def calendar_webhook(request: EventRequest, background_tasks: BackgroundTasks,
                     x_integration_secret: Optional[str] = Header(default=None),
                     db: Session = Depends(get_db)):
    if not settings.integration_secret or x_integration_secret != settings.integration_secret:
        raise HTTPException(status_code=401, detail="Invalid integration secret")
    add_analytics_event(db, "meeting.booked", request.session_id, request.data)
    if request.session_id:
        background_tasks.add_task(sync_lead_background, str(request.session_id), request.data,
                                  ["meeting.booked"])
    return {"accepted": True}


@router.post("/integrations/lead", status_code=202)
def integration_lead_update(request: IntegrationLeadUpdate, background_tasks: BackgroundTasks,
                            x_integration_secret: Optional[str] = Header(default=None),
                            db: Session = Depends(get_db)):
    if not settings.integration_secret or x_integration_secret != settings.integration_secret:
        raise HTTPException(status_code=401, detail="Invalid integration secret")
    conversation = db.get(ConversationDB, str(request.session_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    current = get_lead_profile(db, conversation.id)
    allowed = set(LeadProfile.model_fields) - {"score", "temperature"}
    updates = {key: value for key, value in request.lead.items() if key in allowed}
    lead = current.model_copy(update=updates)
    lead = calculate_lead_score(LeadProfile.model_validate(lead))
    save_lead_profile(db, conversation.id, lead)
    conversation.stage = determine_sales_stage(lead).value
    db.commit()
    payload = lead.model_dump(mode="json") | {"session_id": conversation.id,
                                               "status": conversation.stage}
    background_tasks.add_task(sync_lead_background, conversation.id, payload, [])
    return {"accepted": True, "score": lead.score, "temperature": lead.temperature}


@router.get("/admin/dashboard")
def dashboard(db: Session = Depends(get_db)):
    conversations = db.scalar(select(func.count()).select_from(ConversationDB)) or 0
    visitors = db.scalar(select(func.count(func.distinct(AnalyticsEventDB.session_id))).where(
        AnalyticsEventDB.event_type == "visitor.page_view")) or 0
    leads = db.execute(select(LeadDB)).scalars().all()
    visitor_messages = db.scalar(select(func.count()).select_from(MessageDB).where(
        MessageDB.role == "user")) or 0
    assistant_messages = db.scalar(select(func.count()).select_from(MessageDB).where(
        MessageDB.role == "assistant")) or 0
    meetings = db.scalar(select(func.count()).select_from(AnalyticsEventDB).where(
        AnalyticsEventDB.event_type == "meeting.booked")) or 0
    identified = sum(1 for lead in leads if lead.email or lead.phone)
    services = Counter(service for lead in leads for service in (lead.required_services or []))
    questions = db.execute(select(MessageDB.content).where(MessageDB.role == "user")
                           .order_by(MessageDB.created_at.desc()).limit(100)).scalars().all()
    stages = dict(db.execute(select(ConversationDB.stage, func.count()).group_by(ConversationDB.stage)).all())
    temperatures = dict(db.execute(select(LeadDB.temperature, func.count()).group_by(LeadDB.temperature)).all())
    deliveries = dict(db.execute(select(IntegrationDeliveryDB.status, func.count())
                                 .group_by(IntegrationDeliveryDB.status)).all())
    refresh_settings = {row.key: row.value for row in db.execute(select(IntegrationSettingDB).where(
        IntegrationSettingDB.key.like("knowledge_refresh_%"))).scalars().all()}
    return {
        "totals": {"website_visitors": visitors, "conversations": conversations,
                   "messages": visitor_messages, "leads_generated": identified,
                   "conversion_rate": round((identified / conversations * 100), 1) if conversations else 0,
                   "meetings_booked_or_requested": meetings},
        "popular_services": [{"name": name, "count": count} for name, count in services.most_common(10)],
        "frequently_asked_questions": [{"question": q, "count": count}
                                        for q, count in Counter(questions).most_common(5)],
        "lead_status": stages,
        "lead_temperature": temperatures,
        "sales_performance": {"proposals": sum(1 for lead in leads if lead.wants_proposal),
                              "callbacks": sum(1 for lead in leads if lead.wants_callback),
                              "handover_requests": sum(1 for lead in leads if lead.requested_human)},
        "ai_performance": {
                           "assistant_responses": assistant_messages,
                           "response_coverage_percent": round(
                               assistant_messages / visitor_messages * 100, 1
                           ) if visitor_messages else 0,
                           "visitor_messages_per_conversation": round(
                               visitor_messages / conversations, 2
                           ) if conversations else 0,
                           "integration_deliveries": deliveries,
                           "knowledge_refresh": refresh_settings},
    }


@router.get("/admin/leads")
def list_leads(db: Session = Depends(get_db)):
    rows = db.execute(select(LeadDB, ConversationDB.stage, CrmLeadStateDB).join(
        ConversationDB, LeadDB.conversation_id == ConversationDB.id)
        .outerjoin(CrmLeadStateDB, CrmLeadStateDB.conversation_id == LeadDB.conversation_id)
        .order_by(LeadDB.updated_at.desc())).all()
    return [{"id": lead.id, "session_id": lead.conversation_id, "name": lead.full_name,
             "company": lead.company_name, "email": lead.email, "phone": lead.phone,
             "services": lead.required_services, "score": lead.score,
             "temperature": lead.temperature, "stage": stage,
             "crm_status": crm.status if crm else "new",
             "assigned_to": crm.assigned_to if crm else None,
             "follow_up_at": crm.follow_up_at.isoformat() if crm and crm.follow_up_at else None,
             "notes": crm.notes if crm else None,
             "follow_up_overdue": bool(crm and crm.follow_up_at and crm.follow_up_at < datetime.utcnow()),
             "updated_at": lead.updated_at.isoformat()} for lead, stage, crm in rows]


@router.put("/admin/leads/{session_id}", dependencies=[Depends(require_admin)])
def update_crm_lead(session_id: str, request: CrmLeadUpdate,
                    background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    lead = db.execute(select(LeadDB).where(LeadDB.conversation_id == session_id)).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    state = db.execute(select(CrmLeadStateDB).where(
        CrmLeadStateDB.conversation_id == session_id)).scalar_one_or_none()
    if not state:
        state = CrmLeadStateDB(conversation_id=session_id)
        db.add(state)
    state.status = request.status
    state.assigned_to = request.assigned_to
    state.follow_up_at = request.follow_up_at.replace(tzinfo=None) if request.follow_up_at else None
    state.notes = request.notes
    db.commit()
    add_analytics_event(db, "crm.lead_updated", session_id,
                        {"status": state.status, "assigned_to": state.assigned_to,
                         "follow_up_at": state.follow_up_at.isoformat() if state.follow_up_at else None})
    payload = get_lead_profile(db, session_id).model_dump(mode="json") | {
        "session_id": session_id, "status": state.status,
        "assigned_team": state.assigned_to,
        "follow_up_due": state.follow_up_at.isoformat() if state.follow_up_at else None,
    }
    background_tasks.add_task(sync_lead_background, session_id, payload, [])
    return {"updated": True, "session_id": session_id}


@router.get("/conversations/{session_id}", dependencies=[Depends(require_admin)])
def conversation_history(session_id: str, db: Session = Depends(get_db)):
    conversation = db.get(ConversationDB, session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"session_id": session_id, "stage": conversation.stage,
            "messages": [{"role": message.role, "content": message.content,
                          "sources": message.sources or [], "created_at": message.created_at.isoformat()}
                         for message in conversation.messages]}


@router.get("/conversations/{session_id}/updates")
def conversation_updates(session_id: str, after_id: int = 0, db: Session = Depends(get_db)):
    if not db.get(ConversationDB, session_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = db.execute(select(MessageDB).where(MessageDB.conversation_id == session_id,
                                              MessageDB.id > after_id,
                                              MessageDB.role == "assistant")
                      .order_by(MessageDB.id)).scalars().all()
    return [{"id": row.id, "content": row.content, "sources": row.sources or []} for row in rows]


@router.post("/admin/conversations/{session_id}/reply", dependencies=[Depends(require_admin)])
def human_reply(session_id: str, request: HumanReplyRequest, db: Session = Depends(get_db)):
    conversation = db.get(ConversationDB, session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    message = add_message(db, session_id, "assistant", request.message.strip())
    add_analytics_event(db, "handover.agent_reply", session_id)
    lead = get_lead_profile(db, session_id)
    if not lead.email:
        return {"id": message.id, "delivered": True,
                "email_status": "skipped_no_email"}
    email_delivery = send_visitor_reply(
        db, session_id, lead.email, lead.full_name or "", request.message.strip()
    )
    return {"id": message.id, "delivered": True,
            "email_status": email_delivery.status}


@router.get("/inquiries/{session_id}")
def inquiry_details(session_id: str, db: Session = Depends(get_db)):
    if not db.get(ConversationDB, session_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    lead = get_lead_profile(db, session_id)
    return lead.model_dump(mode="json")


@router.post("/inquiries/{session_id}")
def submit_inquiry(session_id: str, request: InquiryRequest,
                   background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    conversation = db.get(ConversationDB, session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    current = get_lead_profile(db, session_id)
    updates = request.model_dump()
    updates["wants_proposal"] = True
    lead = calculate_lead_score(current.model_copy(update=updates))
    save_lead_profile(db, session_id, lead)
    conversation.stage = determine_sales_stage(lead).value
    db.commit()
    payload = lead.model_dump(mode="json") | {
        "session_id": session_id, "status": conversation.stage,
        "assigned_team": lead.required_services[0] if lead.required_services else "General Sales",
    }
    background_tasks.add_task(sync_lead_background, session_id, payload,
                              ["proposal.requested"])
    add_analytics_event(db, "inquiry.submitted", session_id,
                        {"services": lead.required_services})
    confirmation = (
        "Thank you for submitting the form. We’ll see you at the meeting. "
        "Do you have any further questions? I’ll be here to help."
        if lead.meeting_booked
        else "Thank you for submitting the form. Our team will review your "
             "details. Do you have any further questions? I’ll be here to help."
    )
    confirmation_message = add_message(
        db,
        session_id,
        "assistant",
        confirmation,
    )
    return {"submitted": True, "score": lead.score,
            "temperature": lead.temperature, "status": conversation.stage,
            "chat_message_id": confirmation_message.id,
            "chat_message": confirmation}
