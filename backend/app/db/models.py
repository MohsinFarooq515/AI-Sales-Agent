from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class ConversationDB(Base):
    __tablename__ = "conversations"

    id = Column(
        String(50),
        primary_key=True,
    )

    stage = Column(
        String(50),
        default="discovery",
        nullable=False,
    )

    last_conversion_prompt_turn = Column(Integer, nullable=True)
    attention_offer_shown = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    messages = relationship(
        "MessageDB",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    lead = relationship(
        "LeadDB",
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id = Column(
        String(50),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )

    role = Column(
        String(20),
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    sources = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    conversation = relationship(
        "ConversationDB",
        back_populates="messages",
    )


class LeadDB(Base):
    __tablename__ = "leads"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id = Column(
        String(50),
        ForeignKey("conversations.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    full_name = Column(String(200))
    persona = Column(String(50))
    company_name = Column(String(200))
    email = Column(String(320))
    phone = Column(String(100))
    website_url = Column(String(500))
    industry = Column(String(200))
    business_problem = Column(Text)
    location = Column(String(200))
    budget = Column(String(200))
    timeline = Column(String(200))

    required_services = Column(
        JSON,
        default=list,
        nullable=False,
    )

    wants_meeting = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    meeting_booked = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    wants_callback = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    wants_proposal = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    requested_human = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    score = Column(
        Integer,
        default=0,
        nullable=False,
    )

    temperature = Column(
        String(20),
        default="cold",
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    conversation = relationship(
        "ConversationDB",
        back_populates="lead",
    )


class AnalyticsEventDB(Base):
    __tablename__ = "analytics_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IntegrationDeliveryDB(Base):
    __tablename__ = "integration_deliveries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(50), nullable=False, index=True)
    destination = Column(String(50), nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class GoogleCalendarCredentialDB(Base):
    __tablename__ = "google_calendar_credentials"
    id = Column(Integer, primary_key=True, default=1)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    scope = Column(Text, nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IntegrationSettingDB(Base):
    __tablename__ = "integration_settings"
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CrmLeadStateDB(Base):
    __tablename__ = "crm_lead_states"
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(50), ForeignKey("conversations.id"), unique=True,
                             nullable=False, index=True)
    status = Column(String(50), nullable=False, default="new")
    assigned_to = Column(String(200), nullable=True)
    follow_up_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
