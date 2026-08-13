from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=40)
    company: Optional[str] = Field(default=None, max_length=200)
    source: Optional[str] = Field(default="website", max_length=80)
    budget_range: Optional[str] = Field(default=None, max_length=80)
    timeline: Optional[str] = Field(default=None, max_length=80)
    pain_points: Optional[str] = Field(default=None, max_length=4000)
    notes: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=40)
    company: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = None
    temperature: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    deal_value_estimate: Optional[float] = Field(default=None, ge=0)


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    source: str

    budget_score: float
    authority_score: float
    need_score: float
    timeline_score: float
    fit_score: float
    overall_score: float

    temperature: str
    status: str
    budget_range: Optional[str] = None
    timeline: Optional[str] = None
    pain_points: Optional[str] = None
    notes: Optional[str] = None
    deal_value_estimate: float

    created_at: datetime
    updated_at: datetime


class QualificationAnswer(BaseModel):
    question_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=2000)


class QualifyRequest(BaseModel):
    lead: LeadCreate
    answers: list[QualificationAnswer]
    visit_id: Optional[str] = None


class QualifyResponse(BaseModel):
    lead: LeadOut
    breakdown: dict
    recommended_action: str


class ActivityCreate(BaseModel):
    lead_id: str
    action_type: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=4000)
    meta: Optional[dict] = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    action_type: str
    description: Optional[str] = None
    created_at: datetime


class ChatMessage(BaseModel):
    lead_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=4000)
    history: Optional[list[dict]] = None


class TrackVisitRequest(BaseModel):
    source: Optional[str] = Field(default="landing_page", max_length=80)
    page: Optional[str] = Field(default=None, max_length=500)
    campaign: Optional[str] = Field(default=None, max_length=200)
    medium: Optional[str] = Field(default=None, max_length=100)
    referrer: Optional[str] = Field(default=None, max_length=2000)


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    page: Optional[str] = None
    campaign: Optional[str] = None
    medium: Optional[str] = None
    lead_id: Optional[str] = None
    created_at: datetime
