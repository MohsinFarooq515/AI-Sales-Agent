from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.analytics import require_admin
from app.api.models import MeetingRequest
from app.agent.lead_scoring import calculate_lead_score
from app.core.config import settings
from app.db.database import get_db
from app.db.models import ConversationDB, GoogleCalendarCredentialDB, IntegrationSettingDB
from app.db.repository import (
    add_analytics_event,
    add_message,
    get_lead_profile,
    save_lead_profile,
)
from app.integrations.google_calendar import authorization_url, create_event, exchange_code
from app.integrations.google_sheets import clear_lead_rows
from app.integrations.webhooks import sync_lead_background


router = APIRouter(prefix="/api/google-calendar", tags=["Google Calendar"])


@router.get("/connect", dependencies=[Depends(require_admin)])
def connect():
    return {"authorization_url": authorization_url()}


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    exchange_code(db, code, state)
    return RedirectResponse(f"{settings.app_base_url}/admin?calendar=connected")


@router.get("/status")
def status(db: Session = Depends(get_db)):
    record = db.get(GoogleCalendarCredentialDB, 1)
    sheet = db.get(IntegrationSettingDB, "google_sheets_spreadsheet_id")
    spreadsheet_id = settings.google_sheets_spreadsheet_id or (sheet.value if sheet else None)
    return {"configured": bool(settings.google_client_id and settings.google_client_secret),
            "connected": bool(record),
            "connected_at": record.connected_at.isoformat() if record else None,
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": (f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
                                if spreadsheet_id else None)}


@router.delete("/sheet-records", dependencies=[Depends(require_admin)])
def clear_sheet_records(confirm: str, db: Session = Depends(get_db)):
    if confirm != "CLEAR_GOOGLE_SHEET_RECORDS":
        raise HTTPException(400, "Clear confirmation is incorrect")
    spreadsheet_id = clear_lead_rows(db)
    return {"cleared": True, "spreadsheet_id": spreadsheet_id, "preserved_header": True}


@router.post("/book")
def book(request: MeetingRequest, background_tasks: BackgroundTasks,
         db: Session = Depends(get_db)):
    if not db.get(ConversationDB, str(request.session_id)):
        raise HTTPException(404, "Conversation not found")
    event = create_event(db, request)
    add_analytics_event(db, "meeting.booked", request.session_id,
                        {"event_id": event.get("id"), "html_link": event.get("htmlLink")})
    lead = get_lead_profile(db, str(request.session_id))
    lead.full_name = request.name
    lead.email = request.email
    lead.wants_meeting = True
    lead.meeting_booked = True
    lead = calculate_lead_score(lead)
    save_lead_profile(db, str(request.session_id), lead)
    confirmation = (
        "Thank you for scheduling a meeting. Our team will get back to you. "
        "Please complete this short form so we can match you with the best "
        "professional for your needs."
    )
    confirmation_message = add_message(
        db,
        str(request.session_id),
        "assistant",
        confirmation,
        sources=[{
            "type": "action",
            "action_type": "complete_profile",
            "label": "Complete details form",
            "url": f"{settings.app_base_url}/inquiry",
        }],
    )
    payload = lead.model_dump(mode="json") | {
        "session_id": str(request.session_id), "status": "meeting_booked",
        "meeting_start": request.start.isoformat(), "meeting_url": event.get("hangoutLink"),
    }
    background_tasks.add_task(sync_lead_background, str(request.session_id), payload,
                              ["meeting.booked"])
    return {"booked": True, "event_id": event.get("id"),
            "calendar_url": event.get("htmlLink"),
            "meeting_url": event.get("hangoutLink"),
            "chat_message_id": confirmation_message.id,
            "chat_message": confirmation}
