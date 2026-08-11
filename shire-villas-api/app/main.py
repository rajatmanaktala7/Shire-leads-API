from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import leads, activities, dashboard, ai


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router)
app.include_router(activities.router)
app.include_router(dashboard.router)
app.include_router(ai.router)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENV}


@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "docs": "/docs",
        "health": "/health",
        "dashboard_api": "/dashboard/",
    }


# Serve the static dashboard frontend at /app (index.html + assets)
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
