from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import json
import queue
import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAIError
from sqlalchemy.orm import Session

from app.agent.lead_extractor import (
    LeadExtractor,
    merge_lead_profile,
)
from app.agent.lead_scoring import (
    calculate_lead_score,
)
from app.agent.sales_agent import (
    SalesAgentService,
    extract_explicit_visitor_name,
    extract_initial_name_reply,
)
from app.agent.sales_stage import (
    determine_sales_stage,
)
from app.agent.actions import (
    build_browser_actions,
    determine_conversion_prompt,
    PROMPT_COMPANY_PHONE,
    PROMPT_PHONE,
)

from app.api.models import (
    ChatRequest,
    ChatResponse,
    LeadSummaryResponse,
)

from app.db.database import SessionLocal, get_db
from app.db.repository import (
    add_analytics_event,
    add_message,
    get_lead_profile,
    get_messages,
    get_or_create_conversation,
    save_lead_profile,
)
from app.integrations.webhooks import sync_lead_background


router = APIRouter(
    prefix="/api",
    tags=["AI Sales Agent"],
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

INDEX_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "knowledge_embeddings.json"
)


lead_extractor = LeadExtractor()

sales_agent = SalesAgentService(
    index_file=INDEX_FILE
)

external_executor = ThreadPoolExecutor(max_workers=8)


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return _process_chat(request, background_tasks, db)


def _process_chat(request, background_tasks, db, on_delta=None):

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    # -----------------------------------
    # Conversation
    # -----------------------------------

    conversation = (
        get_or_create_conversation(
            db=db,
            session_id=request.session_id,
        )
    )

    add_message(
        db=db,
        conversation_id=conversation.id,
        role="user",
        content=message,
    )

    # -----------------------------------
    # Restore existing lead
    # -----------------------------------

    lead = get_lead_profile(
        db=db,
        conversation_id=conversation.id,
    )
    # Explicit introductions are deterministic and must not depend on the
    # model-based lead extractor. Persist the name in this isolated session
    # before response generation so the current and later replies can use it.
    explicit_visitor_name = extract_explicit_visitor_name(message)
    if not explicit_visitor_name and len(get_messages(db, conversation.id)) == 1:
        explicit_visitor_name = extract_initial_name_reply(message)
    if explicit_visitor_name:
        lead.full_name = explicit_visitor_name
    previous_score = lead.score
    was_identified = bool(lead.email or lead.phone)
    had_email = bool(lead.email)
    previously_wanted_meeting = lead.wants_meeting
    previously_wanted_proposal = lead.wants_proposal
    previously_requested_human = lead.requested_human

    # -----------------------------------
    # Lead extraction
    # Only visitor messages are used
    # -----------------------------------

    messages = get_messages(
        db=db,
        conversation_id=conversation.id,
    )

    try:
        extraction_future = external_executor.submit(lead_extractor.extract, message)
        retrieval_future = external_executor.submit(sales_agent.retrieve_knowledge, message)
        retrieval_results = retrieval_future.result()
        history = [{"role": item.role, "content": item.content} for item in messages]
        response_language = sales_agent.identify_response_language(message, history)
        extracted = extraction_future.result()
    except OpenAIError as exc:
        raise HTTPException(status_code=503,
                            detail="The AI service is temporarily unavailable. Please retry.") from exc

    # On the opening name question, accept a model-extracted name only when
    # the same conservative deterministic check accepts the visitor's reply.
    # This prevents business descriptions such as "clothing brand" from being
    # persisted as a person's name after the earlier check rejected them.
    if visitor_message_count := sum(1 for item in messages if item.role == "user"):
        if (visitor_message_count == 1 and not explicit_visitor_name
                and extracted.full_name):
            extracted = extracted.model_copy(update={"full_name": None})

    lead = merge_lead_profile(
        current=lead,
        extracted=extracted,
    )

    lead = calculate_lead_score(
        lead
    )

    # -----------------------------------
    # Sales stage
    # -----------------------------------

    stage = determine_sales_stage(
        lead
    )

    visitor_turn = sum(1 for item in messages if item.role == "user")
    if lead.email and not had_email:
        conversation.email_captured_turn = visitor_turn
    conversion_prompt_kind = determine_conversion_prompt(
        message,
        lead,
        visitor_turn,
        conversation.last_conversion_prompt_turn,
        conversation.last_conversion_prompt_kind,
        conversation.email_captured_turn,
    )
    allow_conversion_prompt = conversion_prompt_kind is not None

    # Generate from the updated profile so the same turn can thank a visitor
    # for a newly supplied email and never ask for information just captured.
    response_future = external_executor.submit(
        sales_agent.generate_response,
        message,
        history,
        lead.model_copy(deep=True),
        stage.value,
        retrieval_results,
        response_language,
        allow_conversion_prompt,
        False,
        conversion_prompt_kind,
        on_delta,
    )

    conversation.stage = stage.value

    db.commit()

    save_lead_profile(
        db=db,
        conversation_id=conversation.id,
        lead=lead,
    )

    lead_payload = lead.model_dump(mode="json")
    lead_payload.update({
        "session_id": conversation.id,
        "status": stage.value,
        "assigned_team": (lead.required_services[0] if lead.required_services else "General Sales"),
        "follow_up_due": ((datetime.utcnow() + timedelta(hours=24)).isoformat()
                          if lead.score >= 35 else None),
    })
    notification_events = []
    is_identified = bool(lead.email or lead.phone)
    if is_identified and not was_identified:
        notification_events.append("lead.created")
    if lead.wants_meeting and not previously_wanted_meeting:
        notification_events.append("meeting.requested")
    if lead.wants_proposal and not previously_wanted_proposal:
        notification_events.append("proposal.requested")
    if lead.score >= 70 and previous_score < 70:
        notification_events.append("lead.high_value")
    if lead.requested_human and not previously_requested_human:
        notification_events.append("handover.requested")
    add_analytics_event(db, "conversation.message", conversation.id,
                        {"services": lead.required_services, "stage": stage.value,
                         "page_url": request.page_url})

    # -----------------------------------
    # Generate AI response
    # -----------------------------------

    try:
        result = response_future.result()
    except OpenAIError as exc:
        raise HTTPException(status_code=503,
                            detail="The AI service is temporarily unavailable. Please retry.") from exc

    # -----------------------------------
    # Save response
    # -----------------------------------

    actions = build_browser_actions(
        message,
        result["sources"],
        lead,
        show_conversion=False,
        prompt_kind=conversion_prompt_kind,
    )
    if (any(action["type"] in ("book_meeting", "share_email") for action in actions)
            or conversion_prompt_kind in (PROMPT_PHONE, PROMPT_COMPANY_PHONE)):
        conversation.last_conversion_prompt_turn = visitor_turn
        conversation.last_conversion_prompt_kind = conversion_prompt_kind

    assistant_message = add_message(
        db=db,
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        sources=result["sources"],
    )
    if is_identified:
        complete_messages = get_messages(db=db, conversation_id=conversation.id)
        lead_payload["conversation_history"] = [
            {"role": item.role, "content": item.content,
             "created_at": item.created_at.isoformat()} for item in complete_messages
        ]
        background_tasks.add_task(sync_lead_background, conversation.id,
                                  lead_payload, notification_events)

    # -----------------------------------
    # API response
    # -----------------------------------

    temperature = (
        lead.temperature.value
        if hasattr(
            lead.temperature,
            "value",
        )
        else str(lead.temperature)
    )

    return ChatResponse(
        session_id=conversation.id,
        message_id=assistant_message.id,
        answer=result["answer"],
        sales_stage=stage.value,
        lead=LeadSummaryResponse(
            score=lead.score,
            temperature=temperature,
            full_name=lead.full_name,
            persona=lead.persona,
            company_name=lead.company_name,
            email=lead.email,
            phone=lead.phone,
            website_url=lead.website_url,
            industry=lead.industry,
            required_services=(
                lead.required_services
            ),
        ),
        sources=result["sources"],
        actions=actions,
    )


@router.post("/chat/stream")
def chat_stream(request: ChatRequest, background_tasks: BackgroundTasks):
    """Stream answer deltas, followed by the normal ChatResponse metadata."""
    events = queue.Queue()

    def emit(delta):
        events.put(("delta", delta))

    def process():
        db = SessionLocal()
        try:
            result = _process_chat(request, background_tasks, db, emit)
            events.put(("done", result.model_dump(mode="json")))
        except Exception as exc:
            detail = getattr(exc, "detail", "The chat request failed. Please retry.")
            events.put(("error", str(detail)))
        finally:
            db.close()
            events.put(("close", None))

    def stream_events():
        threading.Thread(target=process, daemon=True).start()
        while True:
            event_type, payload = events.get()
            if event_type == "close":
                break
            yield json.dumps(
                {"type": event_type, "delta" if event_type == "delta" else "data": payload},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        stream_events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background_tasks,
    )
