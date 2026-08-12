from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import leads, activities, dashboard, ai


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Team-Key"],
)

app.include_router(leads.router)
app.include_router(activities.router)
app.include_router(dashboard.router)
app.include_router(ai.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.ENV,
        "version": "2.0.0",
    }


@app.get("/config")
def public_config():
    return {"meta_pixel_id": settings.META_PIXEL_ID}


@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "health": "/health",
        "landing_page": "/app/landing.html",
    }


app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
