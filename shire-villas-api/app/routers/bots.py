from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.security import require_team_key
from app.services.runtime_service import run_once
from app.services.lead_bot_service import (
    BUYER_QUERIES,
    NRI_QUERIES,
    BROKER_QUERIES,
    latest_runs,
    run_buyer_hunter,
    run_broker_hunter,
    run_daily_suite,
    run_final_execution_suite,
    run_pending_enrichment,
    tavily_connection_test,
    tavily_production_search_test,
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
    return await run_once(run_daily_suite)


@router.get("/diagnostics/tavily")
async def tavily_diagnostics():
    return await tavily_connection_test()


@router.get("/diagnostics/tavily-production")
async def tavily_production_diagnostics():
    return await tavily_production_search_test()


async def _run_buyer_background():
    await run_buyer_hunter()


async def _run_nri_background():
    await run_buyer_hunter(NRI_QUERIES, bot_name="NRI Second-Home Hunter")


async def _run_brokers_background():
    await run_broker_hunter()


async def _run_daily_background():
    await run_once(run_daily_suite)


@router.post("/start/buyer")
async def start_buyer(background_tasks: BackgroundTasks):
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    background_tasks.add_task(_run_buyer_background)
    return {"accepted": True, "bot": "Buyer Intent Hunter", "message": "Started in background"}


@router.post("/start/nri")
async def start_nri(background_tasks: BackgroundTasks):
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    background_tasks.add_task(_run_nri_background)
    return {"accepted": True, "bot": "NRI Second-Home Hunter", "message": "Started in background"}


@router.post("/start/brokers")
async def start_brokers(background_tasks: BackgroundTasks):
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    background_tasks.add_task(_run_brokers_background)
    return {"accepted": True, "bot": "Broker & Channel Partner Hunter", "message": "Started in background"}


@router.post("/start/daily-suite")
async def start_daily(background_tasks: BackgroundTasks):
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    background_tasks.add_task(_run_daily_background)
    return {"accepted": True, "bot": "Daily Lead Suite", "message": "Started in background"}

@router.get("/diagnostics/intelligence")
def intelligence_diagnostics():
    return {
        "version": settings.VERSION,
        "search_provider": "tavily" if settings.TAVILY_API_KEY else "brave" if settings.BRAVE_SEARCH_API_KEY else None,
        "groq_classifier": bool(settings.GROQ_API_KEY),
        "apollo_enrichment": bool(settings.APOLLO_API_KEY),
        "require_identifiable_buyer": settings.LEAD_BOT_REQUIRE_IDENTIFIABLE_BUYER,
        "actionable_score": settings.LEAD_BOT_ACTIONABLE_SCORE,
        "min_admission_score": settings.LEAD_BOT_MIN_ADMISSION_SCORE,
        "flowconnect_configured": bool(settings.FLOWCONNECT_WEBHOOK_URL),
        "safety": {
            "invent_contacts": False,
            "noise_classes_rejected": True,
            "crm_requires_verified_contact": True,
        },
    }


@router.post("/run/final-suite")
async def run_final_suite():
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        raise HTTPException(422, "Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY in Railway.")
    return await run_once(run_final_execution_suite)


@router.post("/run/pending-enrichment")
async def run_enrichment():
    return await run_pending_enrichment()
