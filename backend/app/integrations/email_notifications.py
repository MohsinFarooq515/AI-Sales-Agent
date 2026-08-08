import smtplib
from email.message import EmailMessage
from typing import Dict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IntegrationDeliveryDB


EVENT_TITLES = {
    "lead.created": "New sales lead",
    "meeting.requested": "Meeting requested",
    "meeting.booked": "Meeting booked",
    "proposal.requested": "Proposal requested",
    "lead.high_value": "High-value lead identified",
    "handover.requested": "Live-agent handover requested",
}


def _configured():
    return bool(settings.smtp_host and settings.smtp_from_email and
                settings.sales_notification_emails)


def send_notification(db: Session, conversation_id: str, event_type: str, payload: Dict):
    record = IntegrationDeliveryDB(conversation_id=conversation_id, destination="smtp_email",
        event_type=event_type, payload=payload, status="pending")
    db.add(record)
    db.commit()
    if not _configured():
        record.status = "not_configured"
        record.last_error = "SMTP settings or sales recipients are not configured"
        db.commit()
        return record
    title = EVENT_TITLES.get(event_type, event_type.replace(".", " ").title())
    message = EmailMessage()
    message["Subject"] = f"[AI Sales Agent] {title}"
    message["From"] = settings.smtp_from_email
    message["To"] = ", ".join(settings.sales_notification_emails)
    message.set_content(
        f"{title}\n\nName: {payload.get('full_name') or payload.get('name') or 'Not provided'}\n"
        f"Company: {payload.get('company_name') or 'Not provided'}\n"
        f"Email: {payload.get('email') or 'Not provided'}\n"
        f"Phone: {payload.get('phone') or 'Not provided'}\n"
        f"Services: {', '.join(payload.get('required_services', [])) or 'Not provided'}\n"
        f"Score: {payload.get('score', 'Not available')}\n"
        f"Status: {payload.get('status', 'Not available')}\n"
        f"Session: {conversation_id}\n\nOpen CRM: {settings.app_base_url}/admin"
    )
    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        record.status = "delivered"
        record.attempts = 1
        record.last_error = None
    except Exception as exc:
        record.status = "failed"
        record.attempts = 1
        record.last_error = str(exc)[:1000]
    db.commit()
    return record


def notify_background(conversation_id: str, event_type: str, payload: Dict):
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        send_notification(db, conversation_id, event_type, payload)
    finally:
        db.close()
