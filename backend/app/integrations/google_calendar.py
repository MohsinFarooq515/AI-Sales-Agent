import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.db.models import GoogleCalendarCredentialDB


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/spreadsheets",
)
_states = {}


def connection_ready() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def authorization_url() -> str:
    if not connection_ready():
        raise HTTPException(503, "Google OAuth credentials are not configured")
    state = secrets.token_urlsafe(32)
    _states[state] = datetime.utcnow() + timedelta(minutes=10)
    query = urlencode({"client_id": settings.google_client_id,
                       "redirect_uri": settings.google_redirect_uri,
                       "response_type": "code", "scope": " ".join(SCOPES),
                       "access_type": "offline", "prompt": "consent",
                       "include_granted_scopes": "true", "state": state})
    return f"{AUTH_URL}?{query}"


def exchange_code(db: Session, code: str, state: str):
    expiry = _states.pop(state, None)
    if not expiry or expiry < datetime.utcnow():
        raise HTTPException(400, "Invalid or expired OAuth state")
    response = httpx.post(TOKEN_URL, data={"client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret, "code": code,
        "grant_type": "authorization_code", "redirect_uri": settings.google_redirect_uri}, timeout=15)
    if response.is_error:
        raise HTTPException(502, "Google rejected the OAuth token exchange")
    data = response.json()
    record = db.get(GoogleCalendarCredentialDB, 1)
    if not record:
        record = GoogleCalendarCredentialDB(id=1, access_token=encrypt_secret(data["access_token"]),
            expires_at=datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)))
        db.add(record)
    record.access_token = encrypt_secret(data["access_token"])
    if data.get("refresh_token"):
        record.refresh_token = encrypt_secret(data["refresh_token"])
    record.expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600) - 60)
    record.scope = data.get("scope", " ".join(SCOPES))
    db.commit()


def access_token(db: Session) -> str:
    record = db.get(GoogleCalendarCredentialDB, 1)
    if not record:
        raise HTTPException(503, "Google Calendar account is not connected")
    if record.expires_at > datetime.utcnow():
        return decrypt_secret(record.access_token)
    if not record.refresh_token:
        raise HTTPException(503, "Reconnect Google Calendar")
    response = httpx.post(TOKEN_URL, data={"client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": decrypt_secret(record.refresh_token),
        "grant_type": "refresh_token"}, timeout=15)
    if response.is_error:
        raise HTTPException(502, "Google access token refresh failed")
    data = response.json()
    record.access_token = encrypt_secret(data["access_token"])
    record.expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600) - 60)
    db.commit()
    return decrypt_secret(record.access_token)


def create_event(db: Session, meeting):
    token = access_token(db)
    end = meeting.start + timedelta(minutes=meeting.duration_minutes)
    url = EVENTS_URL.format(calendar_id=settings.google_calendar_id)
    availability = httpx.get(url, params={"timeMin": meeting.start.isoformat(),
        "timeMax": end.isoformat(), "singleEvents": "true", "maxResults": 1},
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    if availability.is_error:
        raise HTTPException(502, "Google Calendar availability check failed")
    if availability.json().get("items"):
        raise HTTPException(409, "That time is no longer available. Please choose another time.")
    event = {"summary": f"Sales consultation - {meeting.name}",
             "description": meeting.notes or "Booked through the AI Sales Agent",
             "start": {"dateTime": meeting.start.isoformat(), "timeZone": meeting.timezone},
             "end": {"dateTime": end.isoformat(), "timeZone": meeting.timezone},
             "attendees": [{"email": meeting.email}],
             "conferenceData": {"createRequest": {"requestId": secrets.token_hex(12),
                                                    "conferenceSolutionKey": {"type": "hangoutsMeet"}}}}
    response = httpx.post(url, params={"conferenceDataVersion": 1, "sendUpdates": "all"},
                          headers={"Authorization": f"Bearer {token}"}, json=event, timeout=15)
    if response.is_error:
        raise HTTPException(502, "Google Calendar could not create the meeting")
    return response.json()
