from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class LeadTemperature(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


class SalesStage(str, Enum):
    DISCOVERY = "discovery"
    RECOMMENDATION = "recommendation"
    QUALIFICATION = "qualification"
    CONVERSION = "conversion"
    HANDOVER = "handover"


class LeadProfile(BaseModel):
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website_url: Optional[str] = None
    industry: Optional[str] = None

    required_services: List[str] = Field(
        default_factory=list
    )

    business_problem: Optional[str] = None
    location: Optional[str] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None

    wants_meeting: bool = False
    wants_callback: bool = False
    wants_proposal: bool = False
    requested_human: bool = False

    score: int = 0
    temperature: LeadTemperature = LeadTemperature.COLD

class LeadExtraction(BaseModel):
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website_url: Optional[str] = None
    industry: Optional[str] = None

    required_services: List[str] = Field(
        default_factory=list
    )

    business_problem: Optional[str] = None
    location: Optional[str] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None

    wants_meeting: Optional[bool] = None
    wants_callback: Optional[bool] = None
    wants_proposal: Optional[bool] = None
    requested_human: Optional[bool] = None

class ConversationState(BaseModel):
    session_id: str

    stage: SalesStage = SalesStage.DISCOVERY

    lead: LeadProfile = Field(
        default_factory=LeadProfile
    )

    recommended_services: List[str] = Field(
        default_factory=list
    )

    message_count: int = 0