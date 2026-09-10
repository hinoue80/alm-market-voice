"""
Ingestion orchestrator — runs the full pipeline for all enabled sources.

Flow for each source:
  1. Call the appropriate connector to fetch raw signals (all sources run in parallel)
  2. Upsert raw signals into the signals table (skip duplicates, no LLM call)
  3. Rebuild the topic_summaries rollup for the current week

Enrichment (watsonx.ai) is intentionally decoupled: after ingestion completes,
call the /api/enrich endpoint to process new signals in parallel.
This keeps ingestion fast (seconds, not minutes).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import SessionLocal, Source, Signal, TopicSummary
from app.connectors import (
    fetch_reddit_json,
    fetch_rss,
    fetch_competitor_page,
    clean_signal,
)

logger = logging.getLogger(__name__)

CONNECTOR_MAP = {
    "practitioner_community": fetch_reddit_json,  # Reddit subreddits
    "rss":                    fetch_rss,           # analyst feeds
    "trade_media":            fetch_rss,           # trade media RSS
    "practitioner_pub":       fetch_rss,           # practitioner publication RSS
    "conference":             fetch_competitor_page,  # Tavily crawl (seasonal)
    # Legacy aliases (kept for backward compat during migration)
    "reddit":                 fetch_reddit_json,
    "community":              fetch_rss,
    "industry_news":          fetch_rss,
}


def run_ingestion(source_ids: list[int] | None = None) -> dict[str, Any]:
    """
    Run the full ingestion pipeline.

    Args:
        source_ids: If provided, only ingest these specific source IDs.
                    If None, ingest all enabled sources.

    Returns:
        Summary dict: {total_fetched, total_saved, sources_processed, errors}
    """
    db = SessionLocal()
    summary = {"total_fetched": 0, "total_saved": 0, "sources_processed": 0, "errors": []}

    try:
        query = db.query(Source).filter(Source.enabled == 1)
        if source_ids:
            query = query.filter(Source.id.in_(source_ids))
        sources = query.all()

        logger.info("Starting ingestion for %d sources (parallel fetch)", len(sources))

        # Fetch all sources in parallel — each connector is I/O-bound (HTTP)
        # Skip conference/crawl sources on first pass — Tavily crawl can hang for minutes
        _FAST_TYPES = {"practitioner_community", "rss", "trade_media", "practitioner_pub",
                       "reddit", "community", "industry_news"}
        fast_sources = [s for s in sources if s.source_type in _FAST_TYPES]
        slow_sources = [s for s in sources if s.source_type not in _FAST_TYPES]

        if slow_sources:
            logger.info("Deferring %d slow/crawl sources (conference etc.)", len(slow_sources))

        def _fetch_one(source):
            return source, _ingest_source(db, source)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_one, s): s for s in fast_sources}
            for future in as_completed(futures, timeout=90):
                try:
                    source, fetched = future.result(timeout=60)
                    summary["total_fetched"] += fetched["fetched"]
                    summary["total_saved"] += fetched["saved"]
                    summary["sources_processed"] += 1
                except Exception as exc:
                    src = futures[future]
                    msg = f"Source '{src.name}' failed: {exc}"
                    logger.error(msg)
                    summary["errors"].append(msg)

        # Rebuild topic rollup for current week
        rebuild_topic_summaries(db)
        logger.info("Ingestion complete: %s", summary)

    finally:
        db.close()

    return summary


def _ingest_source(_unused_db: Session, source: Source) -> dict[str, int]:
    """
    Fetch and save signals for a single source.
    Opens its own DB session so this function is safe to call from a thread pool.
    """
    import signal as _signal

    connector = CONNECTOR_MAP.get(source.source_type)
    if connector is None:
        logger.warning("No connector for source_type '%s'", source.source_type)
        return {"fetched": 0, "saved": 0}

    # RSS-based connectors accept source_type to tune the recency gate
    _rss_types = {"rss", "community", "industry_news", "trade_media", "practitioner_pub"}
    try:
        if source.source_type in _rss_types:
            raw = connector(source.url, source_type=source.source_type)
        else:
            raw = connector(source.url)
    except Exception as exc:
        logger.warning("Connector failed for '%s': %s", source.name, exc)
        return {"fetched": 0, "saved": 0}
    raw_signals = [clean_signal(s) for s in raw]
    # Drop signals with empty body after noise filtering (20 chars = at least a meaningful title)
    raw_signals = [s for s in raw_signals if len(s.get("body", "").strip()) >= 20]
    logger.info("Source '%s': fetched %d raw signals (after noise filter)", source.name, len(raw_signals))

    db = SessionLocal()
    saved = 0
    try:
        for raw in raw_signals:
            try:
                signal_data = {
                    "source_id":      source.id,
                    "external_id":    raw.get("external_id"),
                    "title":          raw.get("title", "")[:500],
                    "body":           raw.get("body", ""),
                    "url":            raw.get("url", "")[:1000],
                    "published_at":   raw.get("published_at") or datetime.utcnow(),
                    "collected_at":   datetime.utcnow(),
                    # Legacy enrichment fields — /api/enrich fills them later
                    "topics":         [],
                    "sentiment":      "neutral",
                    "relevance_score": 0.0,
                    "signal_type":    "general",
                    "enriched":       0,
                    # New demand-signal fields (null until enriched)
                    "demand_signal":   None,
                    "problem":         None,
                    "desired_outcome": None,
                    "approach":        None,
                    "persona":         None,
                    "industry":        None,
                    "org_type":        None,
                    "author_type":     None,
                    "evidence_weight": None,
                }

                # Upsert: insert if URL is new; if duplicate just bump collected_at.
                # Uses dialect-agnostic approach — works for both SQLite and PostgreSQL.
                existing = db.query(Signal).filter_by(url=signal_data["url"]).first()
                if existing is None:
                    db.add(Signal(**signal_data))
                    saved += 1
                else:
                    existing.collected_at = signal_data["collected_at"]

            except Exception as exc:
                logger.warning("Failed to save signal from '%s': %s", source.name, exc)

        db.commit()
    finally:
        db.close()

    return {"fetched": len(raw_signals), "saved": saved}


def rebuild_topic_summaries(db: Session) -> None:
    """
    Rebuild the TopicSummary rollup for the current ISO week.
    Deletes existing entries for this week and recalculates from signals.
    """
    today = datetime.utcnow().date()
    week_start = datetime.combine(
        today - timedelta(days=today.weekday()), datetime.min.time()
    )
    week_end = week_start + timedelta(days=7)

    # Delete existing rollup for this week
    db.query(TopicSummary).filter(TopicSummary.week_start == week_start).delete()

    # Fetch all signals from this week
    signals = (
        db.query(Signal)
        .filter(Signal.collected_at >= week_start, Signal.collected_at < week_end)
        .all()
    )

    # Aggregate by topic
    topic_counts: dict[str, int] = defaultdict(int)
    topic_sentiments: dict[str, list[float]] = defaultdict(list)
    topic_sources: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    SENTIMENT_SCORES = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

    for signal in signals:
        topics = signal.topics or []
        source_name = signal.source.name if signal.source else "unknown"
        sentiment_score = SENTIMENT_SCORES.get(signal.sentiment or "neutral", 0.0)

        for topic in topics:
            topic_counts[topic] += 1
            topic_sentiments[topic].append(sentiment_score)
            topic_sources[topic][source_name] += 1

    # Write summaries
    for topic, count in topic_counts.items():
        sentiments = topic_sentiments[topic]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        db.add(TopicSummary(
            topic=topic,
            week_start=week_start,
            mention_count=count,
            avg_sentiment_score=round(avg_sentiment, 3),
            source_breakdown=dict(topic_sources[topic]),
        ))

    db.commit()
    logger.info("Topic summaries rebuilt: %d topics for week of %s", len(topic_counts), week_start.date())
