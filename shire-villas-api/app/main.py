from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.database import init_db
from app.security import require_team_key, verify_team_key, create_session_token
from app.routers import (
    leads, activities, dashboard, ai, organic, partners, referrals,
    marketing, integrations, bots, system,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Team-Key", "Authorization"],
)

for router in [
    leads.router, activities.router, dashboard.router, ai.router, organic.router,
    partners.router, referrals.router, marketing.router, integrations.router,
    bots.router, system.router,
]:
    app.include_router(router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.ENV,
        "version": settings.VERSION,
        "system": "Shire Villas Buyer Intelligence OS V7 Stable Core",
    }


class LoginRequest(BaseModel):
    team_key: str


@app.post("/auth/login")
def auth_login(payload: LoginRequest):
    if not verify_team_key(payload.team_key):
        raise HTTPException(status_code=401, detail="Invalid Team API Key.")
    return {
        "ok": True,
        "token": create_session_token(),
        "expires_in": 43200,
        "version": settings.VERSION,
    }


@app.get("/auth/check", dependencies=[Depends(require_team_key)])
def auth_check():
    return {"ok": True, "authenticated": True, "version": settings.VERSION}


@app.get("/config")
def public_config():
    return {
        "meta_pixel_id": settings.META_PIXEL_ID,
        "flowconnect_enabled": bool(settings.FLOWCONNECT_WEBHOOK_URL),
        "version": settings.VERSION,
    }


@app.get("/")
def root():
    return {
        "project": "Shire Villas AI Revenue OS",
        "version": settings.VERSION,
        "dashboard": "/app/",
        "landing": "/app/landing.html",
        "health": "/health",
        "readiness": "/system/readiness",
    }


app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
