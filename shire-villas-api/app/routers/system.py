from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.security import require_team_key
from app.services.runtime_service import state


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/readiness")
def readiness():
    db_ok = True
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)[:300]

    issues = settings.config_issues()
    return {
        "ok": db_ok and not any(x.level == "ERROR" for x in issues),
        "version": settings.VERSION,
        "database": {"ok": db_ok, "error": db_error},
        "discovery": {
            "tavily": bool(settings.TAVILY_API_KEY),
            "brave": bool(settings.BRAVE_SEARCH_API_KEY),
            "groq": bool(settings.GROQ_API_KEY),
            "apollo": bool(settings.APOLLO_API_KEY),
        },
        "crm": {"flowconnect": bool(settings.FLOWCONNECT_WEBHOOK_URL)},
        "issues": [{"level": x.level, "key": x.key, "message": x.message} for x in issues],
    }


@router.get("/runtime", dependencies=[Depends(require_team_key)])
def runtime():
    return state()


@router.get("/business-policy", dependencies=[Depends(require_team_key)])
def business_policy():
    return {
        "min_budget_cr": settings.SHIRE_MIN_BUDGET_CR,
        "qualified_score": settings.SHIRE_QUALIFIED_SCORE,
        "priority_score": settings.SHIRE_PRIORITY_SCORE,
        "target_locations": settings.SHIRE_TARGET_LOCATIONS,
        "require_named_buyer": settings.LEAD_BOT_REQUIRE_IDENTIFIABLE_BUYER,
        "auto_promote": settings.AUTO_PROMOTE_QUALIFIED_LEADS,
    }
