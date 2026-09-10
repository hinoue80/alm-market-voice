"""
ALM Market Voice — FastAPI application entry point.
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import init_db
from app.api.routes import router
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ALM Market Voice",
    description="Internal IBM market intelligence dashboard for Asset Lifecycle Management",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — allow the React dev server in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)


@app.on_event("startup")
async def on_startup():
    logger.info("Initialising database …")
    init_db()
    logger.info("Starting scheduler …")
    start_scheduler()
    logger.info("ALM Market Voice is ready ✓")


@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()


@app.get("/health")
def health():
    return {"status": "ok", "service": "alm-market-voice"}


# Serve built React frontend in production — MUST be last: html=True is a catch-all
_static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
    logger.info("Serving static frontend from %s", _static_dir)
