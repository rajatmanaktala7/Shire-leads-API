from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import OrganicOpportunity, OpportunityStatus, Lead, LeadStatus, LeadTemperature
from app.schemas.organic import OpportunityCreate, OpportunityUpdate, OpportunityOut
from app.security import require_team_key
from app.services.organic_service import score_opportunity, suggested_response
from app.services.lead_service import log_activity
from app.services.flowconnect_service import sync_lead_by_id

router = APIRouter(prefix="/organic", tags=["organic"], dependencies=[Depends(require_team_key)])


@router.post("/opportunities", response_model=OpportunityOut)
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)):
    # Lightweight dedupe using contact or same URL.
    duplicate = None
    if payload.email or payload.phone or payload.source_url:
        clauses = []
        if payload.email: clauses.append(OrganicOpportunity.email == payload.email)
        if payload.phone: clauses.append(OrganicOpportunity.phone == payload.phone)
        if payload.source_url: clauses.append(OrganicOpportunity.source_url == payload.source_url)
        duplicate = db.query(OrganicOpportunity).filter(or_(*clauses)).first()
    if duplicate:
        return duplicate

    o = OrganicOpportunity(**payload.model_dump())
    o.intent_score = score_opportunity(payload.source_text, payload.location, payload.budget_hint, payload.timeline_hint)
    db.add(o)
    db.flush()
    o.suggested_response = suggested_response(o)
    db.commit(); db.refresh(o)
    return o


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=500)):
    return db.query(OrganicOpportunity).order_by(OrganicOpportunity.intent_score.desc(), OrganicOpportunity.created_at.desc()).limit(limit).all()


@router.put("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity(opportunity_id: str, payload: OpportunityUpdate, db: Session = Depends(get_db)):
    o = db.query(OrganicOpportunity).filter(OrganicOpportunity.id == opportunity_id).first()
    if not o: raise HTTPException(404, "Opportunity not found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"]:
        try: data["status"] = OpportunityStatus(data["status"].upper())
        except ValueError: raise HTTPException(422, "Invalid opportunity status")
    for k,v in data.items(): setattr(o,k,v)
    db.commit(); db.refresh(o)
    return o


@router.post("/opportunities/{opportunity_id}/promote")
def promote_opportunity(opportunity_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    o = db.query(OrganicOpportunity).filter(OrganicOpportunity.id == opportunity_id).first()
    if not o: raise HTTPException(404, "Opportunity not found")
    if o.promoted_lead_id:
        return {"lead_id": o.promoted_lead_id, "already_promoted": True}
    if not o.verified:
        raise HTTPException(422, "Verify the opportunity before promoting it to CRM")
    if not o.phone and not o.email:
        raise HTTPException(422, "Phone or email required before promoting to CRM")

    temp = LeadTemperature.HOT if o.intent_score >= 80 else LeadTemperature.WARM if o.intent_score >= 60 else LeadTemperature.COLD
    lead = Lead(
        name=o.person_name or "Organic prospect",
        phone=o.phone, email=o.email, company=o.brand_company,
        source=f"organic:{o.platform}", overall_score=o.intent_score,
        temperature=temp, status=LeadStatus.NEW,
        budget_range=o.budget_hint, timeline=o.timeline_hint,
        notes=f"Organic opportunity: {o.source_url or ''}"
    )
    db.add(lead); db.commit(); db.refresh(lead)
    o.promoted_lead_id = lead.id
    o.status = OpportunityStatus.PROMOTED
    db.commit()
    log_activity(db, lead.id, "ORGANIC_PROMOTED", f"Promoted from {o.platform} opportunity with score {o.intent_score}")
    background_tasks.add_task(sync_lead_by_id, lead.id)
    return {"lead_id": lead.id, "already_promoted": False}


@router.get("/stats")
def organic_stats(db: Session = Depends(get_db)):
    total = db.query(OrganicOpportunity).count()
    verified = db.query(OrganicOpportunity).filter(OrganicOpportunity.verified == True).count()
    hot = db.query(OrganicOpportunity).filter(OrganicOpportunity.intent_score >= 80).count()
    promoted = db.query(OrganicOpportunity).filter(OrganicOpportunity.status == OpportunityStatus.PROMOTED).count()
    responded = db.query(OrganicOpportunity).filter(OrganicOpportunity.status == OpportunityStatus.RESPONDED).count()
    return {"total": total, "verified": verified, "hot": hot, "promoted": promoted, "responded": responded}
