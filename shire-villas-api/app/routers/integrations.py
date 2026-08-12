from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.lead import Lead, CRMSyncLog
from app.security import require_team_key
from app.services.flowconnect_service import sync_lead_by_id

router=APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(require_team_key)])

@router.get("/flowconnect/status")
def status(db: Session = Depends(get_db)):
    last=db.query(CRMSyncLog).order_by(CRMSyncLog.created_at.desc()).first()
    synced=db.query(CRMSyncLog).filter(CRMSyncLog.status=="SYNCED").count()
    failed=db.query(CRMSyncLog).filter(CRMSyncLog.status=="FAILED").count()
    return {"configured":bool(settings.FLOWCONNECT_WEBHOOK_URL),"synced":synced,"failed":failed,
            "last":{"lead_id":last.lead_id,"status":last.status,"http_status":last.http_status,"created_at":last.created_at.isoformat()} if last else None}

@router.post("/flowconnect/sync/{lead_id}")
def sync(lead_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.query(Lead).filter(Lead.id==lead_id).first(): raise HTTPException(404,"Lead not found")
    background_tasks.add_task(sync_lead_by_id, lead_id)
    return {"queued":True,"lead_id":lead_id}
