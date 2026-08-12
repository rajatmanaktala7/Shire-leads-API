import json
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.lead import LandingPage
from app.schemas.marketing import LandingPageCreate, LandingPageUpdate
from app.security import require_team_key

router = APIRouter(prefix="/marketing", tags=["marketing"])

DEFAULT_CONFIG = {
    "eyebrow": "SIOLIM · NORTH GOA",
    "headline": "A private address in North Goa.",
    "subheadline": "18 ultra-luxury 4BHK villas crafted for second-home owners and investors who value privacy, design and location.",
    "primary_cta": "Check pricing & availability",
    "secondary_cta": "Talk to QBot",
    "hero_image": "",
    "gallery": [],
    "price_label": "Starting from ₹10 Cr",
    "facts": [
        {"value":"18","label":"Exclusive villas"},
        {"value":"4BHK","label":"Private residences"},
        {"value":"Siolim","label":"North Goa"},
    ],
    "about_title": "Designed for a slower, richer Goa.",
    "about_text": "Use this section to explain architecture, landscape, privacy, construction quality and the experience of owning at Shire Villas.",
    "features": [
        {"title":"Private living","text":"Low-density luxury with generous indoor and outdoor spaces."},
        {"title":"Prime North Goa","text":"Positioned for access to Siolim, Assagao, Vagator and the wider North Goa lifestyle."},
        {"title":"Assisted buying","text":"QBot qualifies the requirement before your sales team takes over."},
    ],
    "location_title": "Siolim, North Goa",
    "location_text": "Add your strongest location story, nearby landmarks, dining, beaches, airport access and lifestyle advantages here.",
    "brochure_url": "",
    "video_url": "",
    "seo_title": "Shire Villas | Luxury Villas in Siolim, North Goa",
    "seo_description": "Discover Shire Villas in Siolim, North Goa. Request current pricing, availability and a private presentation.",
}

def serialize(row: LandingPage):
    try: cfg=json.loads(row.config_json or "{}")
    except Exception: cfg={}
    merged={**DEFAULT_CONFIG, **cfg}
    return {"id":row.id,"slug":row.slug,"name":row.name,"config":merged,"active":row.active,"updated_at":row.updated_at.isoformat() if row.updated_at else None}


def ensure_default(db: Session):
    row=db.query(LandingPage).filter(LandingPage.slug=="main").first()
    if not row:
        row=LandingPage(slug="main", name="Main Shire Villas Landing Page", config_json=json.dumps(DEFAULT_CONFIG), active=True)
        db.add(row); db.commit(); db.refresh(row)
    return row

@router.get("/pages/{slug}/public")
def public_page(slug: str, db: Session = Depends(get_db)):
    if slug == "main": ensure_default(db)
    row=db.query(LandingPage).filter(LandingPage.slug==slug, LandingPage.active==True).first()
    if not row: raise HTTPException(404,"Campaign page not found")
    return serialize(row)

@router.get("/pages", dependencies=[Depends(require_team_key)])
def list_pages(db: Session = Depends(get_db)):
    ensure_default(db)
    return [serialize(x) for x in db.query(LandingPage).order_by(LandingPage.updated_at.desc()).all()]

@router.post("/pages", dependencies=[Depends(require_team_key)])
def create_page(payload: LandingPageCreate, db: Session = Depends(get_db)):
    if db.query(LandingPage).filter(LandingPage.slug==payload.slug).first():
        raise HTTPException(409,"Slug already exists")
    row=LandingPage(slug=payload.slug,name=payload.name,config_json=json.dumps(payload.config),active=payload.active)
    db.add(row); db.commit(); db.refresh(row); return serialize(row)

@router.put("/pages/{slug}", dependencies=[Depends(require_team_key)])
def update_page(slug: str, payload: LandingPageUpdate, db: Session = Depends(get_db)):
    row=db.query(LandingPage).filter(LandingPage.slug==slug).first()
    if not row: raise HTTPException(404,"Campaign page not found")
    if payload.name is not None: row.name=payload.name
    if payload.config is not None: row.config_json=json.dumps(payload.config)
    if payload.active is not None: row.active=payload.active
    db.commit(); db.refresh(row); return serialize(row)

@router.post("/upload", dependencies=[Depends(require_team_key)])
async def upload_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(415,"Only image files are allowed")
    data=await file.read()
    if len(data)>8*1024*1024: raise HTTPException(413,"Image must be under 8 MB")
    ext=Path(file.filename or "image.jpg").suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp",".gif"}: ext=".jpg"
    upload_dir=Path(settings.UPLOAD_DIR)
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        upload_dir=Path("uploads"); upload_dir.mkdir(parents=True, exist_ok=True)
    name=f"{uuid.uuid4().hex}{ext}"
    (upload_dir/name).write_bytes(data)
    return {"url":f"/media/{name}","filename":name}
