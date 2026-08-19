from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[UUID] = None
    page_url: Optional[str] = Field(default=None, max_length=2000)


class SourceResponse(BaseModel):
    title: str
    url: str
    score: float


class LeadSummaryResponse(BaseModel):
    score: int
    temperature: str

    full_name: Optional[str] = None
    persona: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None

    required_services: List[str] = Field(
        default_factory=list
    )
    phone: Optional[str] = None
    website_url: Optional[str] = None
    industry: Optional[str] = None


class BrowserActionResponse(BaseModel):
    type: str
    label: str
    url: Optional[str] = None
    fields: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    session_id: str
    message_id: int
    answer: str
    sales_stage: str
    lead: LeadSummaryResponse

    sources: List[SourceResponse] = Field(
        default_factory=list
    )
    actions: List[BrowserActionResponse] = Field(default_factory=list)


class EventRequest(BaseModel):
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,49}$")
    session_id: Optional[UUID] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class IntegrationLeadUpdate(BaseModel):
    session_id: UUID
    lead: Dict[str, Any]


class HumanReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class MeetingRequest(BaseModel):
    session_id: UUID
    start: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    duration_minutes: int = Field(default=30, ge=15, le=120)
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    notes: Optional[str] = Field(default=None, max_length=2000)


class CrmLeadUpdate(BaseModel):
    status: str = Field(pattern=r"^(new|contacted|qualified|proposal|won|lost|handover)$")
    assigned_to: Optional[str] = Field(default=None, max_length=200)
    follow_up_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=4000)


class InquiryRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    company_name: Optional[str] = Field(default=None, max_length=200)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    phone: Optional[str] = Field(default=None, max_length=100)
    website_url: Optional[str] = Field(default=None, max_length=500)
    industry: Optional[str] = Field(default=None, max_length=200)
    required_services: List[str] = Field(default_factory=list, max_length=20)
    business_problem: str = Field(min_length=1, max_length=4000)
