import hashlib
import hmac
import json
from typing import Dict

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IntegrationDeliveryDB
from app.db.database import SessionLocal


DESTINATIONS = {
    "crm": settings.custom_crm_webhook_url,
    "google_sheets": settings.google_sheets_webhook_url,
    "notification": settings.notification_webhook_url,
}


def _signature(body: bytes) -> str:
    if not settings.integration_secret:
        return ""
    return hmac.new(settings.integration_secret.encode(), body, hashlib.sha256).hexdigest()


def deliver(db: Session, conversation_id: str, destination: str, event_type: str, payload: Dict):
    record = IntegrationDeliveryDB(conversation_id=conversation_id, destination=destination,
                                   event_type=event_type, payload=payload)
    db.add(record)
    db.commit()
    url = DESTINATIONS.get(destination, "")
    if not url:
        record.status = "not_configured"
        record.last_error = f"{destination} webhook is not configured"
        db.commit()
        return record
    body = json.dumps({"event": event_type, "data": payload}, default=str).encode()
    headers = {"Content-Type": "application/json"}
    signature = _signature(body)
    if signature:
        headers["X-Sales-Agent-Signature"] = signature
    try:
        record.attempts += 1
        response = httpx.post(url, content=body, headers=headers, timeout=8.0)
        response.raise_for_status()
        record.status = "delivered"
        record.last_error = None
    except Exception as exc:
        record.status = "failed"
        record.last_error = str(exc)[:1000]
    db.commit()
    return record


def sync_lead(db: Session, conversation_id: str, payload: Dict, events):
    if settings.custom_crm_webhook_url:
        deliver(db, conversation_id, "crm", "lead.updated", payload)
    if settings.google_sheets_webhook_url:
        deliver(db, conversation_id, "google_sheets", "lead.updated", payload)
    for event_type in events:
        deliver(db, conversation_id, "notification", event_type, payload)


def sync_lead_background(conversation_id: str, payload: Dict, events):
    db = SessionLocal()
    try:
        sync_lead(db, conversation_id, payload, events)
        from app.integrations.email_notifications import send_notification
        for event_type in events:
            send_notification(db, conversation_id, event_type, payload)
        try:
            from app.integrations.google_sheets import sync_lead_to_sheet
            sync_lead_to_sheet(db, payload)
        except Exception as exc:
            record = IntegrationDeliveryDB(conversation_id=conversation_id,
                destination="google_sheets_oauth", event_type="lead.updated", payload=payload,
                status="failed", attempts=1, last_error=str(exc)[:1000])
            db.add(record)
            db.commit()
    finally:
        db.close()
