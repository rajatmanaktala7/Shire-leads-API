from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Visit
from app.security import require_team_key
from app.services.lead_service import get_dashboard_stats

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_team_key)],
)


@router.get("/")
def dashboard(db: Session = Depends(get_db)):
    data = get_dashboard_stats(db)
    data["website_visits"] = db.query(Visit).count()
    return data
