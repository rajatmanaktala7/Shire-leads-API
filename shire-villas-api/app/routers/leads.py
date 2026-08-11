import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead, LeadStatus
from app.schemas.lead import (
    LeadCreate, LeadUpdate, LeadOut, QualifyRequest, QualifyResponse,
)
from app.services.lead_service import score_from_answers, recommended_action, log_activity

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("/", response_model=LeadOut)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    log_activity(db, lead.id, "LEAD_CREATED", f"Lead created via {lead.source}")
    return lead


@router.get("/", response_model=list[LeadOut])
def list_leads(
    db: Session = Depends(get_db),
    temperature: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = db.query(Lead)
    if temperature:
        q = q.filter(Lead.temperature == temperature.upper())
    if status:
        q = q.filter(Lead.status == status.upper())
    if search:
        like = f"%{search}%"
        q = q.filter(
            (Lead.name.ilike(like)) | (Lead.email.ilike(like)) | (Lead.company.ilike(like))
        )
    return q.order_by(Lead.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.put("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: str, payload: LeadUpdate, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(lead, key, value)

    db.commit()
    db.refresh(lead)
    log_activity(db, lead.id, "STAGE_CHANGE", f"Lead updated: {list(data.keys())}")
    return lead


@router.delete("/{lead_id}")
def delete_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()
    return {"deleted": True, "id": lead_id}


@router.post("/qualify", response_model=QualifyResponse)
def qualify_lead(payload: QualifyRequest, db: Session = Depends(get_db)):
    """
    Takes raw lead info + a list of Q&A answers, runs BANT scoring,
    creates the lead already scored, and logs the qualification activity.
    """
    answers_map = {a.question_id: a.answer for a in payload.answers}
    result = score_from_answers(answers_map)

    lead = Lead(
        **payload.lead.model_dump(),
        budget_score=result["budget_score"],
        authority_score=result["authority_score"],
        need_score=result["need_score"],
        timeline_score=result["timeline_score"],
        fit_score=result["fit_score"],
        overall_score=result["overall_score"],
        temperature=result["temperature"],
        status=LeadStatus.QUALIFIED,
        raw_answers=json.dumps(answers_map),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    log_activity(
        db, lead.id, "QUALIFICATION_COMPLETE",
        f"Scored {result['overall_score']} — {result['temperature'].value}",
    )

    return QualifyResponse(
        lead=lead,
        breakdown={
            "budget": result["budget_score"],
            "authority": result["authority_score"],
            "need": result["need_score"],
            "timeline": result["timeline_score"],
            "fit": result["fit_score"],
        },
        recommended_action=recommended_action(result["temperature"]),
    )
