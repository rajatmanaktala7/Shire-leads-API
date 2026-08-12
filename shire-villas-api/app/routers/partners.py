from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.lead import Partner
from app.schemas.organic import PartnerCreate, PartnerOut
from app.security import require_team_key

router = APIRouter(prefix="/partners", tags=["partners"], dependencies=[Depends(require_team_key)])

@router.post("/", response_model=PartnerOut)
def create_partner(payload: PartnerCreate, db: Session = Depends(get_db)):
    p = Partner(**payload.model_dump())
    db.add(p); db.commit(); db.refresh(p); return p

@router.get("/", response_model=list[PartnerOut])
def list_partners(db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=500)):
    return db.query(Partner).order_by(Partner.score.desc(), Partner.created_at.desc()).limit(limit).all()
