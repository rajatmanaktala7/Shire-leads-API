from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.lead import Referral, Lead, LeadStatus, LeadTemperature, ReferralStatus
from app.schemas.organic import ReferralCreate, ReferralOut
from app.security import require_team_key
from app.services.lead_service import log_activity
from app.services.flowconnect_service import sync_lead_by_id

router = APIRouter(prefix="/referrals", tags=["referrals"])

@router.post("/", response_model=ReferralOut)
def public_create_referral(payload: ReferralCreate, db: Session = Depends(get_db)):
    if not payload.consent_confirmed:
        raise HTTPException(422, "Prospect consent must be confirmed before submitting a referral")
    if not payload.prospect_phone and not payload.prospect_email:
        raise HTTPException(422, "Prospect phone or email is required")
    r = Referral(**payload.model_dump())
    db.add(r); db.commit(); db.refresh(r); return r

@router.get("/", response_model=list[ReferralOut], dependencies=[Depends(require_team_key)])
def list_referrals(db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=500)):
    return db.query(Referral).order_by(Referral.created_at.desc()).limit(limit).all()

@router.post("/{referral_id}/promote", dependencies=[Depends(require_team_key)])
def promote_referral(referral_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    r = db.query(Referral).filter(Referral.id == referral_id).first()
    if not r: raise HTTPException(404, "Referral not found")
    if r.lead_id: return {"lead_id": r.lead_id, "already_promoted": True}
    lead = Lead(name=r.prospect_name, phone=r.prospect_phone, email=r.prospect_email,
                source="referral", status=LeadStatus.NEW, temperature=LeadTemperature.WARM,
                overall_score=65, notes=f"Referred by {r.referrer_name}. {r.notes or ''}")
    db.add(lead); db.commit(); db.refresh(lead)
    r.lead_id = lead.id; r.status = ReferralStatus.QUALIFIED; db.commit()
    log_activity(db, lead.id, "REFERRAL_PROMOTED", f"Referral from {r.referrer_name}")
    background_tasks.add_task(sync_lead_by_id, lead.id)
    return {"lead_id": lead.id, "already_promoted": False}
