import json
import logging
import httpx
from app.config import settings
from app.database import SessionLocal
from app.models.lead import Lead, CRMSyncLog

logger=logging.getLogger(__name__)

def configured() -> bool:
    return bool(settings.FLOWCONNECT_WEBHOOK_URL)

def lead_payload(lead: Lead) -> dict:
    return {
        "event":"shire.lead.upsert",
        "external_id":lead.id,
        "source":lead.source,
        "contact":{
            "name":lead.name,
            "phone":lead.phone,
            "email":lead.email,
            "company":lead.company,
        },
        "qualification":{
            "temperature":lead.temperature.value if hasattr(lead.temperature,"value") else str(lead.temperature),
            "status":lead.status.value if hasattr(lead.status,"value") else str(lead.status),
            "overall_score":lead.overall_score,
            "budget_range":lead.budget_range,
            "timeline":lead.timeline,
            "notes":lead.notes,
            "estimated_deal_value":lead.deal_value_estimate,
        },
        "project":"Shire Villas",
        "project_location":"Siolim, North Goa",
    }

def sync_lead_by_id(lead_id: str) -> None:
    db=SessionLocal()
    try:
        lead=db.query(Lead).filter(Lead.id==lead_id).first()
        if not lead: return
        log=CRMSyncLog(lead_id=lead.id, provider="flowconnect", status="PENDING")
        db.add(log); db.commit(); db.refresh(log)
        if not configured():
            log.status="NOT_CONFIGURED"; log.response_text="FLOWCONNECT_WEBHOOK_URL not configured"; db.commit(); return
        headers={"Content-Type":"application/json"}
        if settings.FLOWCONNECT_API_KEY:
            headers["Authorization"]=f"Bearer {settings.FLOWCONNECT_API_KEY}"
        if settings.FLOWCONNECT_WEBHOOK_SECRET:
            headers["X-Webhook-Secret"]=settings.FLOWCONNECT_WEBHOOK_SECRET
        try:
            with httpx.Client(timeout=15.0) as client:
                r=client.post(settings.FLOWCONNECT_WEBHOOK_URL, headers=headers, json=lead_payload(lead))
            log.http_status=str(r.status_code)
            log.response_text=(r.text or "")[:2000]
            log.status="SYNCED" if 200 <= r.status_code < 300 else "FAILED"
        except Exception as exc:
            logger.exception("Flowconnect sync failed")
            log.status="FAILED"; log.response_text=str(exc)[:2000]
        db.commit()
    finally:
        db.close()
