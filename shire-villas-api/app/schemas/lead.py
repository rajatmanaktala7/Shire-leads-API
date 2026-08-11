from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    source: Optional[str] = "website"
    budget_range: Optional[str] = None
    timeline: Optional[str] = None
    pain_points: Optional[str] = None
    notes: Optional[str] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    temperature: Optional[str] = None
    notes: Optional[str] = None
    deal_value_estimate: Optional[float] = None


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
    question_id: str
    answer: str


class QualifyRequest(BaseModel):
    lead: LeadCreate
    answers: list[QualificationAnswer]


class QualifyResponse(BaseModel):
    lead: LeadOut
    breakdown: dict
    recommended_action: str


class ActivityCreate(BaseModel):
    lead_id: str
    action_type: str
    description: Optional[str] = None
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
    message: str
    history: Optional[list[dict]] = None
