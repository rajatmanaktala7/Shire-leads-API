from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.lead_service import get_dashboard_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
def dashboard(db: Session = Depends(get_db)):
    return get_dashboard_stats(db)
