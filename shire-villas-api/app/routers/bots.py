from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.security import require_team_key
from app.services.lead_bot_service import (
    BUYER_QUERIES,
    NRI_QUERIES,
    BROKER_QUERIES,
    latest_runs,
    run_buyer_hunter,
    run_broker_hunter,
    run_daily_suite,
)

router = APIRouter(
    prefix="/bots",
    tags=["lead-bots"],
    dependencies=[Depends(require_team_key)],
)


@router.get("/status")
def bot_status(db: Session = Depends(get_db)):
    provider = None
    if settings.TAVILY_API_KEY:
        provider = "tavily"
    elif settings.BRAVE_SEARCH_API_KEY:
        provider = "brave"

    runs = latest_runs(db, 8)
    return {
        "configured": bool(provider),
        "provider": provider,
        "min_score": settings.LEAD_BOT_MIN_SCORE,
        "time_range": settings.LEAD_BOT_TIME_RANGE,
        "groq_quality_gate": bool(settings.GROQ_API_KEY),
        "last_runs": [
            {
                "id": r.id,
                "bot_name": r.bot_name,
                "provider": r.provider,
                "status": r.status,
                "queries_run": r.queries_run,
                "results_seen": r.results_seen,
                "opportunities_created": r.opportunities_created,
                "partners_created": r.partners_created,
                "duplicates_skipped": r.duplicates_skipped,
                "low_quality_skipped": r.low_quality_skipped,
                "error_text": r.error_text,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ],
    }


@router.get("/query-pack")
def query_pack():
    return {
        "buyer_intent_queries": BUYER_QUERIES,
        "nri_queries": NRI_QUERIES,
        "broker_queries": BROKER_QUERIES,
    }


@router.post("/run/buyer")
async def run_buyer():
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    return await run_buyer_hunter()


@router.post("/run/nri")
async def run_nri():
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    return await run_buyer_hunter(NRI_QUERIES, bot_name="NRI Second-Home Hunter")


@router.post("/run/brokers")
async def run_brokers():
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    return await run_broker_hunter()


@router.post("/run/daily-suite")
async def run_daily():
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    return await run_daily_suite()
