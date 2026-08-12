from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_db
from app.security import require_team_key
from app.routers import leads, activities, dashboard, ai, organic, partners, referrals, marketing, integrations

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate(); init_db(); yield

app = FastAPI(title=settings.PROJECT_NAME, version="4.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                   allow_credentials=False,
                   allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
                   allow_headers=["Content-Type","X-Team-Key"])
app.include_router(leads.router)
app.include_router(activities.router)
app.include_router(dashboard.router)
app.include_router(ai.router)
app.include_router(organic.router)
app.include_router(partners.router)
app.include_router(referrals.router)
app.include_router(marketing.router)
app.include_router(integrations.router)

@app.get("/health")
def health(): return {"status":"ok","env":settings.ENV,"version":"4.2.0","system":"Shire Villas AI Revenue OS V4.2"}


@app.get("/auth/check", dependencies=[Depends(require_team_key)])
def auth_check():
    """Fast team-key validation. Does not touch the database."""
    return {"ok": True, "authenticated": True, "version": "4.2.0"}

@app.get("/config")
def public_config(): return {"meta_pixel_id":settings.META_PIXEL_ID,"flowconnect_enabled":bool(settings.FLOWCONNECT_WEBHOOK_URL)}

@app.get("/")
def root(): return {"project":"Shire Villas AI Revenue OS","dashboard":"/app/","landing":"/app/landing.html","health":"/health"}

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
