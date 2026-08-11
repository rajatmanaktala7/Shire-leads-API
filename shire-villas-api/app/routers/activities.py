from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lead import ActivityCreate, ActivityOut
from app.services.lead_service import log_activity
from app.models.lead import Activity

router = APIRouter(prefix="/activities", tags=["activities"])


@router.post("/", response_model=ActivityOut)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    activity = log_activity(
        db, payload.lead_id, payload.action_type,
        payload.description or "", payload.meta,
    )
    return activity


@router.get("/", response_model=list[ActivityOut])
def list_activities(db: Session = Depends(get_db), limit: int = 50):
    return (
        db.query(Activity)
        .order_by(Activity.created_at.desc())
        .limit(limit)
        .all()
    )
