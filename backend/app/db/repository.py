import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import LeadProfile
from app.db.models import (
    AnalyticsEventDB,
    ConversationDB,
    LeadDB,
    MessageDB,
)


def get_or_create_conversation(
    db: Session,
    session_id: Optional[str] = None,
) -> ConversationDB:
    session_key = str(session_id) if session_id else None
    if session_id:
        conversation = db.get(
            ConversationDB,
            session_key,
        )

        if conversation:
            return conversation

    conversation = ConversationDB(
        id=session_key or str(uuid.uuid4())
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


def add_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    sources=None,
) -> MessageDB:

    message = MessageDB(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def get_messages(
    db: Session,
    conversation_id: str,
) -> List[MessageDB]:

    statement = (
        select(MessageDB)
        .where(
            MessageDB.conversation_id
            == conversation_id
        )
        .order_by(MessageDB.id)
    )

    return list(
        db.execute(
            statement
        ).scalars().all()
    )


def get_lead_profile(
    db: Session,
    conversation_id: str,
) -> LeadProfile:

    statement = select(LeadDB).where(
        LeadDB.conversation_id
        == conversation_id
    )

    record = db.execute(
        statement
    ).scalar_one_or_none()

    if not record:
        return LeadProfile()

    return LeadProfile(
        full_name=record.full_name,
        persona=getattr(record, "persona", None),
        company_name=record.company_name,
        email=record.email,
        phone=record.phone,
        website_url=record.website_url,
        industry=record.industry,
        required_services=(
            record.required_services or []
        ),
        business_problem=record.business_problem,
        location=record.location,
        budget=record.budget,
        timeline=record.timeline,
        wants_meeting=record.wants_meeting,
        meeting_booked=getattr(record, "meeting_booked", False),
        wants_callback=record.wants_callback,
        wants_proposal=record.wants_proposal,
        requested_human=record.requested_human,
        score=record.score,
        temperature=record.temperature,
    )


def save_lead_profile(
    db: Session,
    conversation_id: str,
    lead: LeadProfile,
) -> LeadDB:

    statement = select(LeadDB).where(
        LeadDB.conversation_id
        == conversation_id
    )

    record = db.execute(
        statement
    ).scalar_one_or_none()

    if not record:
        record = LeadDB(
            conversation_id=conversation_id
        )
        db.add(record)

    record.full_name = lead.full_name
    record.persona = lead.persona
    record.company_name = lead.company_name
    record.email = lead.email
    record.phone = lead.phone
    record.website_url = lead.website_url
    record.industry = lead.industry
    record.required_services = (
        lead.required_services
    )
    record.business_problem = (
        lead.business_problem
    )
    record.location = lead.location
    record.budget = lead.budget
    record.timeline = lead.timeline

    record.wants_meeting = (
        lead.wants_meeting
    )
    record.meeting_booked = lead.meeting_booked
    record.wants_callback = (
        lead.wants_callback
    )
    record.wants_proposal = (
        lead.wants_proposal
    )
    record.requested_human = (
        lead.requested_human
    )

    record.score = lead.score

    record.temperature = (
        lead.temperature.value
        if hasattr(
            lead.temperature,
            "value",
        )
        else str(lead.temperature)
    )

    db.commit()
    db.refresh(record)

    return record


def add_analytics_event(db: Session, event_type: str, session_id=None, data=None):
    event = AnalyticsEventDB(event_type=event_type,
                             session_id=str(session_id) if session_id else None,
                             data=data or {})
    db.add(event)
    db.commit()
    return event
