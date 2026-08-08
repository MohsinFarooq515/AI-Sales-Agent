import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env", override=False)


def _csv(name: str, default: str = "") -> List[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


@dataclass(frozen=True)
class Settings:
    allowed_origins: List[str]
    company_phone: str
    custom_crm_webhook_url: str
    google_sheets_webhook_url: str
    notification_webhook_url: str
    integration_secret: str
    admin_api_key: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_calendar_id: str
    google_sheets_spreadsheet_id: str
    app_base_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    sales_notification_emails: List[str]
    smtp_use_tls: bool
    smtp_use_ssl: bool
    token_encryption_key: str


settings = Settings(
    allowed_origins=_csv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"),
    company_phone=os.getenv("COMPANY_PHONE", "+16263818293"),
    custom_crm_webhook_url=os.getenv("CUSTOM_CRM_WEBHOOK_URL", ""),
    google_sheets_webhook_url=os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", ""),
    notification_webhook_url=os.getenv("NOTIFICATION_WEBHOOK_URL", ""),
    integration_secret=os.getenv("INTEGRATION_SECRET", ""),
    admin_api_key=os.getenv("ADMIN_API_KEY", ""),
    google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/google-calendar/callback"),
    google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
    google_sheets_spreadsheet_id=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", ""),
    app_base_url=os.getenv("APP_BASE_URL", "http://127.0.0.1:8000"),
    smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
    smtp_port=int(os.getenv("SMTP_PORT", "587")),
    smtp_username=os.getenv("SMTP_USERNAME", "muhammadmohsinfh@gmail.com"),
    smtp_password=os.getenv("SMTP_PASSWORD", ""),
    smtp_from_email=os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USERNAME", "muhammadmohsinfh@gmail.com")),
    sales_notification_emails=_csv("SALES_NOTIFICATION_EMAILS", "mmohsinfh@gmail.com"),
    smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"),
    smtp_use_ssl=os.getenv("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes"),
    token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY", ""),
)
