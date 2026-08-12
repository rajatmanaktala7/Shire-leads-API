from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lead import ChatMessage
from app.services import ai_service
from app.services.lead_service import log_activity
from app.models.lead import Lead

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/health")
async def ai_health():
    available = await ai_service.is_available()
    return {
        "groq_configured": available,
        "mode": "groq" if available else "rule_based_fallback",
    }


@router.post("/chat")
async def chat(payload: ChatMessage, db: Session = Depends(get_db)):
    result = await ai_service.chat_with_ai(payload.message, payload.history)

    # Do not expose provider/internal exceptions to the browser.
    result.pop("error", None)

    if payload.lead_id:
        lead = db.query(Lead).filter(Lead.id == payload.lead_id).first()
        if lead:
            log_activity(
                db,
                payload.lead_id,
                "AI_RESPONSE",
                f"[{result['source']}] {result['reply'][:120]}",
            )

    return result
