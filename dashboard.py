from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.lead import Visit, OrganicOpportunity, OpportunityStatus, Partner, Referral
from app.security import require_team_key
from app.services.lead_service import get_dashboard_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_team_key)])

@router.get("/")
def dashboard(db: Session = Depends(get_db)):
    data = get_dashboard_stats(db)
    visits = db.query(Visit).count()
    opps = db.query(OrganicOpportunity).count()
    verified = db.query(OrganicOpportunity).filter(OrganicOpportunity.verified == True).count()
    hot_opps = db.query(OrganicOpportunity).filter(OrganicOpportunity.intent_score >= 80).count()
    promoted = db.query(OrganicOpportunity).filter(OrganicOpportunity.status == OpportunityStatus.PROMOTED).count()
    data.update({
        "website_visits": visits,
        "visit_to_lead_rate": round((data["total_leads"] / visits) * 100, 1) if visits else 0,
        "organic_opportunities": opps,
        "verified_opportunities": verified,
        "hot_opportunities": hot_opps,
        "organic_promoted": promoted,
        "partners": db.query(Partner).count(),
        "referrals": db.query(Referral).count(),
    })
    return data
