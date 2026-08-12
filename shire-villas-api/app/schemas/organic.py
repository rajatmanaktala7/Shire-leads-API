from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class OpportunityCreate(BaseModel):
    person_name: Optional[str] = Field(default=None, max_length=150)
    brand_company: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=255)
    platform: str = Field(default="web", max_length=80)
    source_url: Optional[str] = Field(default=None, max_length=2000)
    source_text: str = Field(min_length=5, max_length=10000)
    location: Optional[str] = Field(default=None, max_length=200)
    budget_hint: Optional[str] = Field(default=None, max_length=100)
    timeline_hint: Optional[str] = Field(default=None, max_length=100)
    intent_type: Optional[str] = Field(default=None, max_length=100)
    assigned_to: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=4000)


class OpportunityUpdate(BaseModel):
    status: Optional[str] = None
    verified: Optional[bool] = None
    assigned_to: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=4000)


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    person_name: Optional[str] = None
    brand_company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    platform: str
    source_url: Optional[str] = None
    source_text: str
    location: Optional[str] = None
    budget_hint: Optional[str] = None
    timeline_hint: Optional[str] = None
    intent_type: Optional[str] = None
    intent_score: float
    status: str
    verified: bool
    assigned_to: Optional[str] = None
    suggested_response: Optional[str] = None
    promoted_lead_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PartnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    company: Optional[str] = Field(default=None, max_length=200)
    partner_type: str = Field(default="broker", max_length=80)
    city: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=255)
    website: Optional[str] = Field(default=None, max_length=2000)
    specialization: Optional[str] = Field(default=None, max_length=250)
    score: float = Field(default=0, ge=0, le=100)
    assigned_to: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=4000)


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    company: Optional[str] = None
    partner_type: str
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    specialization: Optional[str] = None
    score: float
    status: str
    assigned_to: Optional[str] = None
    created_at: datetime


class ReferralCreate(BaseModel):
    referrer_name: str = Field(min_length=1, max_length=150)
    referrer_phone: Optional[str] = Field(default=None, max_length=40)
    referrer_email: Optional[str] = Field(default=None, max_length=255)
    prospect_name: str = Field(min_length=1, max_length=150)
    prospect_phone: Optional[str] = Field(default=None, max_length=40)
    prospect_email: Optional[str] = Field(default=None, max_length=255)
    consent_confirmed: bool = False
    notes: Optional[str] = Field(default=None, max_length=4000)


class ReferralOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    referrer_name: str
    prospect_name: str
    prospect_phone: Optional[str] = None
    prospect_email: Optional[str] = None
    consent_confirmed: bool
    status: str
    lead_id: Optional[str] = None
    created_at: datetime
