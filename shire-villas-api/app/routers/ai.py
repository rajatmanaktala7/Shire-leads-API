from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lead import ChatMessage
from app.services import ai_service
from app.services.lead_service import log_activity

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
    if payload.lead_id:
        log_activity(
            db, payload.lead_id, "AI_RESPONSE",
            f"[{result['source']}] {result['reply'][:120]}",
        )
    return result
