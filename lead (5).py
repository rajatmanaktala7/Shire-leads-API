import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, Text, Enum, ForeignKey, Boolean
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


class OpportunityStatus(str, enum.Enum):
    NEW = "NEW"
    REVIEW = "REVIEW"
    VERIFIED = "VERIFIED"
    CONTACTED = "CONTACTED"
    RESPONDED = "RESPONDED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class PartnerStatus(str, enum.Enum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"


class ReferralStatus(str, enum.Enum):
    NEW = "NEW"
    QUALIFIED = "QUALIFIED"
    SITE_VISIT = "SITE_VISIT"
    NEGOTIATION = "NEGOTIATION"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class Visit(Base):
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
    owner = Column(String, nullable=True)
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
    activities = relationship("Activity", back_populates="lead", cascade="all, delete-orphan")
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


class OrganicOpportunity(Base):
    __tablename__ = "organic_opportunities"
    id = Column(String, primary_key=True, default=gen_id)
    person_name = Column(String, nullable=True)
    brand_company = Column(String, nullable=True)
    phone = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True, index=True)
    platform = Column(String, nullable=False, default="web")
    source_url = Column(Text, nullable=True)
    source_text = Column(Text, nullable=False)
    location = Column(String, nullable=True)
    budget_hint = Column(String, nullable=True)
    timeline_hint = Column(String, nullable=True)
    intent_type = Column(String, nullable=True)
    intent_score = Column(Float, default=0)
    status = Column(Enum(OpportunityStatus), default=OpportunityStatus.NEW)
    verified = Column(Boolean, default=False)
    assigned_to = Column(String, nullable=True)
    suggested_response = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    promoted_lead_id = Column(String, ForeignKey("leads.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Partner(Base):
    __tablename__ = "partners"
    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    company = Column(String, nullable=True)
    partner_type = Column(String, default="broker")
    city = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(Text, nullable=True)
    specialization = Column(String, nullable=True)
    score = Column(Float, default=0)
    status = Column(Enum(PartnerStatus), default=PartnerStatus.NEW)
    assigned_to = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Referral(Base):
    __tablename__ = "referrals"
    id = Column(String, primary_key=True, default=gen_id)
    referrer_name = Column(String, nullable=False)
    referrer_phone = Column(String, nullable=True)
    referrer_email = Column(String, nullable=True)
    prospect_name = Column(String, nullable=False)
    prospect_phone = Column(String, nullable=True)
    prospect_email = Column(String, nullable=True)
    consent_confirmed = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    status = Column(Enum(ReferralStatus), default=ReferralStatus.NEW)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class LandingPage(Base):
    __tablename__ = "landing_pages"
    id = Column(String, primary_key=True, default=gen_id)
    slug = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    config_json = Column(Text, nullable=False, default="{}")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class CRMSyncLog(Base):
    __tablename__ = "crm_sync_logs"
    id = Column(String, primary_key=True, default=gen_id)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    provider = Column(String, default="flowconnect", nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    http_status = Column(String, nullable=True)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
