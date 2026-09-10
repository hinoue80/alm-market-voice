"""
APScheduler-based weekly scheduler.
Runs the full ingestion pipeline every Monday at 06:00 UTC.
Also exposes a manual trigger endpoint hook.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.ingestion import run_ingestion

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")

    _scheduler.add_job(
        func=_weekly_job,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="weekly_ingestion",
        name="Weekly market signal ingestion",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1h late if server was down
    )

    _scheduler.start()
    logger.info("Scheduler started — weekly ingestion runs every Monday 06:00 UTC")


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def _weekly_job() -> None:
    logger.info("Weekly ingestion job triggered by scheduler")
    try:
        summary = run_ingestion()
        logger.info("Weekly ingestion finished: %s", summary)
    except Exception as exc:
        logger.error("Weekly ingestion job failed: %s", exc)
