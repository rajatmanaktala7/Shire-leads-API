import csv
import hashlib
import io
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead, LeadStatus, LeadTemperature, Visit
from app.schemas.lead import (
    LeadCreate,
    LeadUpdate,
    LeadOut,
    QualifyRequest,
    QualifyResponse,
    TrackVisitRequest,
    VisitOut,
)
from app.security import require_team_key
from app.services.lead_service import (
    score_from_answers,
    recommended_action,
    log_activity,
)

router = APIRouter(prefix="/leads", tags=["leads"])


# -----------------------------
# PUBLIC ENDPOINTS
# -----------------------------

@router.post("/track", response_model=VisitOut)
def track_visit(payload: TrackVisitRequest, db: Session = Depends(get_db)):
    """
    Record an anonymous session/visit.

    IMPORTANT: this does NOT create a CRM lead. A lead is created only after
    qualification/contact capture.
    """
    visit = Visit(
        source=(payload.source or "landing_page").strip(),
        page=payload.page,
        campaign=payload.campaign,
        medium=payload.medium,
        referrer=payload.referrer,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit


@router.post("/qualify", response_model=QualifyResponse)
def qualify_lead(payload: QualifyRequest, db: Session = Depends(get_db)):
    answers_map = {a.question_id: a.answer for a in payload.answers}
    result = score_from_answers(answers_map)

    # Require a real contact method before turning an anonymous session into a lead.
    if not payload.lead.email and not payload.lead.phone:
        raise HTTPException(
            status_code=422,
            detail="Phone number or email is required to create a qualified lead.",
        )

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

    # Link the anonymous visit to this real lead, if supplied.
    if payload.visit_id:
        visit = db.query(Visit).filter(Visit.id == payload.visit_id).first()
        if visit and visit.lead_id is None:
            visit.lead_id = lead.id
            db.commit()

    log_activity(
        db,
        lead.id,
        "QUALIFICATION_COMPLETE",
        f"Scored {result['overall_score']} - {result['temperature'].value}",
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


# -----------------------------
# TEAM-ONLY ENDPOINTS
# -----------------------------

@router.post("/", response_model=LeadOut, dependencies=[Depends(require_team_key)])
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    log_activity(db, lead.id, "LEAD_CREATED", f"Lead created via {lead.source}")
    return lead


@router.get("/", response_model=list[LeadOut], dependencies=[Depends(require_team_key)])
def list_leads(
    db: Session = Depends(get_db),
    temperature: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = db.query(Lead)

    if temperature:
        try:
            temp_enum = LeadTemperature(temperature.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid temperature.")
        q = q.filter(Lead.temperature == temp_enum)

    if status:
        try:
            status_enum = LeadStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid status.")
        q = q.filter(Lead.status == status_enum)

    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            (Lead.name.ilike(like))
            | (Lead.email.ilike(like))
            | (Lead.phone.ilike(like))
            | (Lead.company.ilike(like))
        )

    return q.order_by(Lead.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/export/meta-audience", dependencies=[Depends(require_team_key)])
def export_meta_audience(
    db: Session = Depends(get_db),
    temperature: str | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=100),
):
    q = db.query(Lead).filter(
        (Lead.email.isnot(None)) | (Lead.phone.isnot(None))
    )

    if temperature:
        try:
            temp_enum = LeadTemperature(temperature.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid temperature.")
        q = q.filter(Lead.temperature == temp_enum)

    if min_score is not None:
        q = q.filter(Lead.overall_score >= min_score)

    leads = q.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "phone"])

    for lead in leads:
        email_hash = ""
        if lead.email:
            email_hash = hashlib.sha256(
                lead.email.strip().lower().encode("utf-8")
            ).hexdigest()

        phone_hash = ""
        if lead.phone:
            digits = re.sub(r"\D", "", lead.phone)
            if digits:
                phone_hash = hashlib.sha256(digits.encode("utf-8")).hexdigest()

        if email_hash or phone_hash:
            writer.writerow([email_hash, phone_hash])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=meta_custom_audience.csv"
        },
    )


@router.get("/{lead_id}", response_model=LeadOut, dependencies=[Depends(require_team_key)])
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.put("/{lead_id}", response_model=LeadOut, dependencies=[Depends(require_team_key)])
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    data = payload.model_dump(exclude_unset=True)

    if "status" in data and data["status"] is not None:
        try:
            data["status"] = LeadStatus(data["status"].upper())
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid status.")

    if "temperature" in data and data["temperature"] is not None:
        try:
            data["temperature"] = LeadTemperature(
                data["temperature"].upper()
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid temperature.")

    for key, value in data.items():
        setattr(lead, key, value)

    db.commit()
    db.refresh(lead)
    log_activity(
        db,
        lead.id,
        "STAGE_CHANGE",
        f"Lead updated: {list(data.keys())}",
    )
    return lead


@router.delete("/{lead_id}", dependencies=[Depends(require_team_key)])
def delete_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    db.delete(lead)
    db.commit()
    return {"deleted": True, "id": lead_id}
