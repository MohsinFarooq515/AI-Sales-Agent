import json
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IntegrationSettingDB
from app.integrations.google_calendar import access_token


SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
HEADERS = ["Session ID", "Updated At", "Name", "Company", "Email", "Phone", "Website",
           "Industry", "Services", "Problem", "Budget", "Timeline", "Score", "Temperature",
           "Status", "Assigned Team", "Follow-up Due", "Conversation History"]


def _request(method, url, token, **kwargs):
    response = httpx.request(method, url, headers={"Authorization": f"Bearer {token}"},
                             timeout=15, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def _spreadsheet_id(db: Session, token: str) -> str:
    if settings.google_sheets_spreadsheet_id:
        return settings.google_sheets_spreadsheet_id
    saved = db.get(IntegrationSettingDB, "google_sheets_spreadsheet_id")
    if saved:
        return saved.value
    result = _request("POST", SHEETS_API, token,
                      json={"properties": {"title": "AI Sales Agent Leads"},
                            "sheets": [{"properties": {"title": "Leads"}}]})
    spreadsheet_id = result["spreadsheetId"]
    db.add(IntegrationSettingDB(key="google_sheets_spreadsheet_id", value=spreadsheet_id))
    db.commit()
    _request("PUT", f"{SHEETS_API}/{spreadsheet_id}/values/Leads!A1:R1",
             token, params={"valueInputOption": "RAW"}, json={"values": [HEADERS]})
    return spreadsheet_id


def sync_lead_to_sheet(db: Session, payload):
    token = access_token(db)
    spreadsheet_id = _spreadsheet_id(db, token)
    session_id = str(payload["session_id"])
    values_url = f"{SHEETS_API}/{spreadsheet_id}/values/{quote('Leads!A:A', safe='!')}"
    existing = _request("GET", values_url, token).get("values", [])
    row_number = next((index for index, row in enumerate(existing, 1)
                       if row and row[0] == session_id), None)
    history = json.dumps(payload.get("conversation_history", []), ensure_ascii=False)
    row = [session_id, payload.get("updated_at", ""), payload.get("full_name", ""),
           payload.get("company_name", ""), payload.get("email", ""), payload.get("phone", ""),
           payload.get("website_url", ""), payload.get("industry", ""),
           ", ".join(payload.get("required_services", [])), payload.get("business_problem", ""),
           payload.get("budget", ""), payload.get("timeline", ""), payload.get("score", 0),
           payload.get("temperature", "cold"), payload.get("status", ""),
           payload.get("assigned_team", ""), payload.get("follow_up_due", ""), history]
    if row_number:
        url = f"{SHEETS_API}/{spreadsheet_id}/values/Leads!A{row_number}:R{row_number}"
        _request("PUT", url, token, params={"valueInputOption": "RAW"}, json={"values": [row]})
    else:
        url = f"{SHEETS_API}/{spreadsheet_id}/values/Leads!A:R:append"
        _request("POST", url, token, params={"valueInputOption": "RAW",
                                             "insertDataOption": "INSERT_ROWS"},
                 json={"values": [row]})
    return spreadsheet_id


def clear_lead_rows(db: Session):
    """Clear lead data rows while preserving the spreadsheet and header row."""
    token = access_token(db)
    spreadsheet_id = _spreadsheet_id(db, token)
    clear_range = quote("Leads!A2:R", safe="!")
    _request("POST", f"{SHEETS_API}/{spreadsheet_id}/values/{clear_range}:clear",
             token, json={})
    # Reassert the expected header so the clean sheet remains ready for new leads.
    _request("PUT", f"{SHEETS_API}/{spreadsheet_id}/values/Leads!A1:R1",
             token, params={"valueInputOption": "RAW"}, json={"values": [HEADERS]})
    return spreadsheet_id
