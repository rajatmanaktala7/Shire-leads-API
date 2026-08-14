from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import (
    Lead,
    LeadStatus,
    LeadTemperature,
    OrganicOpportunity,
    OpportunityStatus,
)
from app.schemas.organic import OpportunityCreate, OpportunityOut, OpportunityUpdate
from app.security import require_team_key
from app.services.flowconnect_service import sync_lead_by_id
from app.services.lead_intelligence_service import (
    ai_classify,
    build_intelligence_payload,
    deterministic_score,
    domain,
    dump_intelligence_notes,
    enrich_candidate,
    parse_intelligence_notes,
)
from app.services.lead_service import log_activity
from app.services.organic_service import score_opportunity, suggested_response

router = APIRouter(prefix="/organic", tags=["organic"], dependencies=[Depends(require_team_key)])


def _to_intelligence_row(o: OrganicOpportunity) -> dict:
    intel = parse_intelligence_notes(o.notes)
    breakdown = intel.get("score_breakdown") or {}
    contact_status = intel.get("contact_status") or ("MANUAL_VERIFIED" if o.verified else "NOT_FOUND")
    return {
        "id": o.id,
        "person_name": o.person_name,
        "brand_company": o.brand_company,
        "phone": o.phone,
        "email": o.email,
        "platform": o.platform,
        "source_url": o.source_url,
        "source_text": o.source_text,
        "location": o.location,
        "budget_hint": o.budget_hint,
        "timeline_hint": o.timeline_hint,
        "intent_type": o.intent_type,
        "intent_score": o.intent_score,
        "status": o.status.value if hasattr(o.status, "value") else str(o.status),
        "verified": bool(o.verified),
        "assigned_to": o.assigned_to,
        "suggested_response": o.suggested_response,
        "promoted_lead_id": o.promoted_lead_id,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
        "classification": intel.get("classification"),
        "band": intel.get("band") or o.intent_type,
        "ai_confidence": intel.get("ai_confidence"),
        "ai_reason": intel.get("ai_reason"),
        "score_breakdown": breakdown,
        "purpose": intel.get("purpose"),
        "authority": intel.get("authority"),
        "contact_status": contact_status,
        "contact_evidence_urls": intel.get("contact_evidence_urls") or [],
        "linkedin_url": intel.get("linkedin_url"),
        "missing_qualification": intel.get("missing_qualification") or [],
        "actionable": bool((o.phone or o.email) and o.intent_score >= 70 and (o.intent_type or "") != "REJECT"),
    }


@router.post("/opportunities", response_model=OpportunityOut)
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)):
    duplicate = None
    if payload.email or payload.phone or payload.source_url:
        clauses = []
        if payload.email: clauses.append(OrganicOpportunity.email == payload.email)
        if payload.phone: clauses.append(OrganicOpportunity.phone == payload.phone)
        if payload.source_url: clauses.append(OrganicOpportunity.source_url == payload.source_url)
        duplicate = db.query(OrganicOpportunity).filter(or_(*clauses)).first()
    if duplicate:
        return duplicate

    o = OrganicOpportunity(**payload.model_dump())
    o.intent_score = score_opportunity(payload.source_text, payload.location, payload.budget_hint, payload.timeline_hint)
    db.add(o); db.flush()
    o.suggested_response = suggested_response(o)
    db.commit(); db.refresh(o)
    return o


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=500)):
    return db.query(OrganicOpportunity).order_by(OrganicOpportunity.intent_score.desc(), OrganicOpportunity.created_at.desc()).limit(limit).all()


@router.get("/intelligence")
def list_intelligence(
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=500),
    actionable_only: bool = False,
):
    rows = db.query(OrganicOpportunity).order_by(OrganicOpportunity.intent_score.desc(), OrganicOpportunity.created_at.desc()).limit(limit).all()
    out = [_to_intelligence_row(x) for x in rows]
    if actionable_only:
        out = [x for x in out if x["actionable"]]
    return out


@router.put("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity(opportunity_id: str, payload: OpportunityUpdate, db: Session = Depends(get_db)):
    o = db.query(OrganicOpportunity).filter(OrganicOpportunity.id == opportunity_id).first()
    if not o: raise HTTPException(404, "Opportunity not found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"]:
        try: data["status"] = OpportunityStatus(data["status"].upper())
        except ValueError: raise HTTPException(422, "Invalid opportunity status")
    for k, v in data.items(): setattr(o, k, v)
    db.commit(); db.refresh(o)
    return o


@router.post("/opportunities/{opportunity_id}/enrich")
async def enrich_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    o = db.query(OrganicOpportunity).filter(OrganicOpportunity.id == opportunity_id).first()
    if not o: raise HTTPException(404, "Opportunity not found")

    title = (parse_intelligence_notes(o.notes).get("source_title") or o.person_name or "Web opportunity")
    ai = await ai_classify(title, o.source_text, o.source_url or "")
    enrichment = await enrich_candidate(title, o.source_text, o.source_url or "", ai)
    score = deterministic_score(o.source_text, ai["classification"], enrichment.get("phone") or o.phone, enrichment.get("email") or o.email)
    if o.phone and not enrichment.get("phone"): enrichment["phone"] = o.phone
    if o.email and not enrichment.get("email"): enrichment["email"] = o.email
    if o.person_name and not ai.get("person_name"): ai["person_name"] = o.person_name
    if o.brand_company and not ai.get("company"): ai["company"] = o.brand_company

    intel = build_intelligence_payload(title, o.source_url or "", ai, score, enrichment)
    o.person_name = ai.get("person_name") or o.person_name
    o.brand_company = ai.get("company") or o.brand_company
    o.phone = enrichment.get("phone") or o.phone
    o.email = enrichment.get("email") or o.email
    o.location = ai.get("location") or score.get("location") or o.location
    o.budget_hint = ai.get("budget_hint") or score.get("budget_hint") or o.budget_hint
    o.timeline_hint = ai.get("timeline_hint") or score.get("timeline_hint") or o.timeline_hint
    o.intent_type = intel["band"]
    o.intent_score = score["total"]
    o.verified = enrichment.get("contact_status") in {"PUBLIC_FOUND", "VERIFIED_PROVIDER"} or o.verified
    o.notes = dump_intelligence_notes(intel, "Re-enriched from dashboard.")
    o.suggested_response = suggested_response(o)
    db.commit(); db.refresh(o)
    return _to_intelligence_row(o)


@router.post("/opportunities/{opportunity_id}/promote")
def promote_opportunity(opportunity_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    o = db.query(OrganicOpportunity).filter(OrganicOpportunity.id == opportunity_id).first()
    if not o: raise HTTPException(404, "Opportunity not found")
    if o.promoted_lead_id:
        return {"lead_id": o.promoted_lead_id, "already_promoted": True}
    if not o.verified:
        raise HTTPException(422, "Verify the opportunity/contact before promoting it to CRM")
    if not o.phone and not o.email:
        raise HTTPException(422, "Phone or email required before promoting to CRM")

    intel = parse_intelligence_notes(o.notes)
    if intel and intel.get("classification") not in {"REAL_BUYER", "POSSIBLE_BUYER"}:
        raise HTTPException(422, "Only genuine buyer classifications can be promoted to CRM")

    temp = LeadTemperature.HOT if o.intent_score >= 80 else LeadTemperature.WARM if o.intent_score >= 70 else LeadTemperature.COLD
    notes = (
        f"Organic buyer opportunity. Source: {o.source_url or ''}\n"
        f"Purpose: {intel.get('purpose') or 'Unknown'}\n"
        f"Authority: {intel.get('authority') or 'Unknown'}\n"
        f"AI reason: {intel.get('ai_reason') or ''}\n"
        f"Missing qualification: {', '.join(intel.get('missing_qualification') or [])}"
    )[:3900]
    lead = Lead(
        name=o.person_name or "Organic prospect",
        phone=o.phone, email=o.email, company=o.brand_company,
        source=f"organic:{o.platform}", overall_score=o.intent_score,
        temperature=temp, status=LeadStatus.NEW,
        budget_range=o.budget_hint, timeline=o.timeline_hint,
        notes=notes,
    )
    db.add(lead); db.commit(); db.refresh(lead)
    o.promoted_lead_id = lead.id
    o.status = OpportunityStatus.PROMOTED
    db.commit()
    log_activity(db, lead.id, "ORGANIC_PROMOTED", f"Promoted from {o.platform} with Shire score {o.intent_score}")
    background_tasks.add_task(sync_lead_by_id, lead.id)
    return {"lead_id": lead.id, "already_promoted": False, "flowconnect_queued": True}


@router.get("/stats")
def organic_stats(db: Session = Depends(get_db)):
    rows = db.query(OrganicOpportunity).all()
    intelligence = [_to_intelligence_row(x) for x in rows]
    total = len(rows)
    verified = sum(1 for x in intelligence if x["verified"])
    actionable = sum(1 for x in intelligence if x["actionable"])
    priority = sum(1 for x in intelligence if x["band"] == "PRIORITY_BUYER")
    hot = sum(1 for x in intelligence if x["band"] in {"PRIORITY_BUYER", "HOT_BUYER"})
    qualified = sum(1 for x in intelligence if x["band"] in {"PRIORITY_BUYER", "HOT_BUYER", "QUALIFIED_BUYER"})
    contactable = sum(1 for x in intelligence if x["phone"] or x["email"])
    enrichment_pending = sum(1 for x in intelligence if x["band"] != "REJECT" and not (x["phone"] or x["email"]))
    promoted = sum(1 for x in rows if x.status == OpportunityStatus.PROMOTED)
    responded = sum(1 for x in rows if x.status == OpportunityStatus.RESPONDED)
    return {
        "total": total, "verified": verified, "hot": hot, "priority": priority,
        "qualified": qualified, "contactable": contactable, "actionable": actionable,
        "enrichment_pending": enrichment_pending, "promoted": promoted, "responded": responded,
    }
