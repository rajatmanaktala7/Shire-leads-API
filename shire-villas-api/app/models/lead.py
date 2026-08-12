import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LeadTemperature(str, enum.Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"
    UNQUALIFIED = "UNQUALIFIED"


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    QUALIFIED = "QUALIFIED"
    SITE_VISIT_SCHEDULED = "SITE_VISIT_SCHEDULED"
    NEGOTIATION = "NEGOTIATION"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class Visit(Base):
    """
    Anonymous website/session visit.

    A visit is intentionally NOT a lead. It becomes linked to a Lead only after
    the visitor supplies contact information and finishes qualification.
    """
    __tablename__ = "visits"

    id = Column(String, primary_key=True, default=gen_id)
    source = Column(String, default="landing_page", nullable=False)
    page = Column(String, nullable=True)
    campaign = Column(String, nullable=True)
    medium = Column(String, nullable=True)
    referrer = Column(Text, nullable=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    lead = relationship("Lead", back_populates="visits")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)
    company = Column(String, nullable=True)
    source = Column(String, default="website", nullable=False)

    budget_score = Column(Float, default=0)
    authority_score = Column(Float, default=0)
    need_score = Column(Float, default=0)
    timeline_score = Column(Float, default=0)
    fit_score = Column(Float, default=0)
    overall_score = Column(Float, default=0)

    temperature = Column(Enum(LeadTemperature), default=LeadTemperature.COLD)
    status = Column(Enum(LeadStatus), default=LeadStatus.NEW)

    budget_range = Column(String, nullable=True)
    timeline = Column(String, nullable=True)
    pain_points = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    deal_value_estimate = Column(Float, default=0)

    raw_answers = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    activities = relationship(
        "Activity", back_populates="lead", cascade="all, delete-orphan"
    )
    visits = relationship("Visit", back_populates="lead")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, default=gen_id)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    action_type = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    lead = relationship("Lead", back_populates="activities")
