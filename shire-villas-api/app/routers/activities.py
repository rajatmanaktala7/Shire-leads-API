from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lead import ActivityCreate, ActivityOut
from app.services.lead_service import log_activity
from app.models.lead import Activity, Lead
from app.security import require_team_key

router = APIRouter(
    prefix="/activities",
    tags=["activities"],
    dependencies=[Depends(require_team_key)],
)


@router.post("/", response_model=ActivityOut)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    if not db.query(Lead).filter(Lead.id == payload.lead_id).first():
        raise HTTPException(status_code=404, detail="Lead not found")

    return log_activity(
        db,
        payload.lead_id,
        payload.action_type,
        payload.description or "",
        payload.meta,
    )


@router.get("/", response_model=list[ActivityOut])
def list_activities(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
):
    return (
        db.query(Activity)
        .order_by(Activity.created_at.desc())
        .limit(limit)
        .all()
    )
