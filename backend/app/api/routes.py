"""
FastAPI route definitions for ALM Market Voice.

Endpoints:
  GET  /api/sources                    — list all sources
  PUT  /api/sources/{id}/toggle        — enable/disable a source
  GET  /api/signals                    — paginated signal feed with filters
  GET  /api/topics                     — trending topics (current week)
  GET  /api/topics/history             — topic trend over N weeks
  GET  /api/topics/signals             — signals tagged with a topic
  GET  /api/demand-signals             — aggregated demand signal radar (with display_label)
  GET  /api/demand-signals/detail      — raw signals for a demand signal
  GET  /api/demand-signals/labels      — all distinct demand signal labels
  POST /api/demand-signals/merge       — merge one label into another (dedup)
  POST /api/ingest                     — manually trigger ingestion (admin)
  GET  /api/ingest/status              — last ingestion summary
  POST /api/enrich                     — LLM enrichment on existing signals
  GET  /api/enrich/status              — enrichment progress
  GET  /api/enrich/providers           — active LLM provider status
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import get_db, Source, Signal, TopicSummary, DemandSignal
from app.ingestion import run_ingestion, rebuild_topic_summaries
from app.enrichment import enrich_signal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_last_ingestion: dict[str, Any] = {}


# ── Sources ──────────────────────────────────────────────────────────────────

@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    sources = db.query(Source).order_by(Source.source_type, Source.name).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "source_type": s.source_type,
            "url": s.url,
            "enabled": bool(s.enabled),
        }
        for s in sources
    ]


@router.put("/sources/{source_id}/toggle")
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.enabled = 0 if source.enabled else 1
    db.commit()
    return {"id": source.id, "name": source.name, "enabled": bool(source.enabled)}


# ── Signals ──────────────────────────────────────────────────────────────────

@router.get("/signals")
def list_signals(
    source_types: str = Query(default=""),
    source_ids: str = Query(default=""),
    sentiment: str = Query(default=""),
    signal_type: str = Query(default=""),
    author_type: str = Query(default=""),
    topic: str = Query(default=""),
    days: int = Query(default=90, ge=1, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(Signal).join(Source).filter(
        Signal.published_at >= since,
        Source.enabled == 1,
    )

    if source_types:
        types = [t.strip() for t in source_types.split(",") if t.strip()]
        q = q.filter(Source.source_type.in_(types))

    if source_ids:
        ids = [int(i) for i in source_ids.split(",") if i.strip().isdigit()]
        q = q.filter(Signal.source_id.in_(ids))

    if sentiment:
        q = q.filter(Signal.sentiment == sentiment)

    if signal_type:
        q = q.filter(Signal.signal_type == signal_type)

    if author_type:
        q = q.filter(Signal.author_type == author_type)

    if topic:
        q = q.filter(Signal.topics.cast(str).ilike(f"%{topic}%"))

    total = q.count()
    signals = (
        q.order_by(desc(Signal.published_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [_signal_to_dict(s) for s in signals],
    }


# ── Topics ───────────────────────────────────────────────────────────────────

@router.get("/topics")
def get_topics(
    weeks: int = Query(default=4, ge=1, le=12),
    limit: int = Query(default=20, ge=5, le=50),
    source_types: str = Query(default=""),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(weeks=weeks)
    q = db.query(
        TopicSummary.topic,
        func.sum(TopicSummary.mention_count).label("total_mentions"),
        func.avg(TopicSummary.avg_sentiment_score).label("avg_sentiment"),
    ).filter(TopicSummary.week_start >= since)

    results = (
        q.group_by(TopicSummary.topic)
        .order_by(desc("total_mentions"))
        .limit(limit)
        .all()
    )

    return [
        {
            "topic": r.topic,
            "mention_count": int(r.total_mentions),
            "avg_sentiment": round(float(r.avg_sentiment or 0), 3),
            "sentiment_label": _sentiment_label(float(r.avg_sentiment or 0)),
        }
        for r in results
    ]


@router.get("/topics/history")
def get_topic_history(
    topic: str = Query(...),
    weeks: int = Query(default=8, ge=2, le=52),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(weeks=weeks)
    rows = (
        db.query(TopicSummary)
        .filter(TopicSummary.topic == topic, TopicSummary.week_start >= since)
        .order_by(TopicSummary.week_start)
        .all()
    )
    return [
        {
            "week_start": r.week_start.strftime("%Y-%m-%d"),
            "mention_count": r.mention_count,
            "avg_sentiment": round(r.avg_sentiment_score or 0, 3),
            "source_breakdown": r.source_breakdown,
        }
        for r in rows
    ]


@router.get("/topics/signals")
def get_topic_signals(
    topic: str = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    signals = (
        db.query(Signal)
        .join(Source)
        .filter(
            Signal.topics.cast(str).ilike(f"%{topic}%"),
            Source.enabled == 1,
        )
        .order_by(desc(Signal.published_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "title": s.title,
            "source_name": s.source.name if s.source else "",
            "source_type": s.source.source_type if s.source else "",
            "published_at": s.published_at.strftime("%b %d, %Y") if s.published_at else "",
            "url": s.url,
            "signal_type": s.signal_type,
        }
        for s in signals
    ]


# ── Demand Signals ───────────────────────────────────────────────────────────

@router.get("/demand-signals")
def get_demand_signals(
    source_ids: str = Query(default=""),
    source_types: str = Query(default=""),
    author_type: str = Query(default=""),       # practitioner | vendor | unknown
    min_weight: int = Query(default=0, ge=0, le=5),
    days: int = Query(default=180, ge=1, le=730),
    limit: int = Query(default=30, ge=5, le=100),
    db: Session = Depends(get_db),
):
    """
    Return aggregated demand signal radar — signals grouped by demand_signal label,
    sorted by (signal_count * avg_evidence_weight) momentum score.

    Builds the rollup on-the-fly from enriched signals so it stays fresh
    without a separate scheduled job.
    """
    since = datetime.utcnow() - timedelta(days=days)
    q = (
        db.query(Signal)
        .join(Source)
        .filter(
            Signal.enriched == 1,
            Signal.demand_signal.isnot(None),
            Signal.demand_signal != "",
            Signal.published_at >= since,
            Source.enabled == 1,
        )
    )

    if source_ids:
        ids = [int(i) for i in source_ids.split(",") if i.strip().isdigit()]
        q = q.filter(Signal.source_id.in_(ids))

    if source_types:
        types = [t.strip() for t in source_types.split(",") if t.strip()]
        q = q.filter(Source.source_type.in_(types))

    if author_type:
        q = q.filter(Signal.author_type == author_type)

    if min_weight > 0:
        q = q.filter(Signal.evidence_weight >= min_weight)

    signals = q.all()

    # ── helper: kebab-case label → human-readable display label ──────────────
    _ABBREVS = {"ai", "iot", "iiot", "eam", "cmms", "esg", "ot", "it", "roi", "tco", "fm", "hvac"}

    def _display(label: str) -> str:
        return " ".join(w.upper() if w in _ABBREVS else w.capitalize() for w in label.split("-"))

    # Aggregate by demand_signal label
    buckets: dict[str, dict] = defaultdict(lambda: {
        "signal_count": 0,
        "evidence_weights": [],
        "industries": set(),
        "personas": set(),
        "source_types": set(),
        "problems": [],
        "outcomes": [],
        "last_seen": None,
    })

    for sig in signals:
        label = sig.demand_signal
        b = buckets[label]
        b["signal_count"] += 1
        if sig.evidence_weight is not None:
            b["evidence_weights"].append(sig.evidence_weight)
        if sig.industry and sig.industry not in ("unknown", ""):
            b["industries"].add(sig.industry)
        if sig.persona and sig.persona not in ("unknown", ""):
            b["personas"].add(sig.persona)
        if sig.source and sig.source.source_type:
            b["source_types"].add(sig.source.source_type)
        if sig.problem and len(b["problems"]) < 3:
            b["problems"].append(sig.problem)
        if sig.desired_outcome and len(b["outcomes"]) < 3:
            b["outcomes"].append(sig.desired_outcome)
        if sig.published_at:
            if b["last_seen"] is None or sig.published_at > b["last_seen"]:
                b["last_seen"] = sig.published_at

    # Build result list, compute momentum = count × avg_evidence_weight
    rows = []
    for label, b in buckets.items():
        avg_w = (sum(b["evidence_weights"]) / len(b["evidence_weights"])
                 if b["evidence_weights"] else 0)
        rows.append({
            "label":              label,
            "display_label":      _display(label),
            "signal_count":       b["signal_count"],
            "evidence_weight_avg": round(avg_w, 2),
            "momentum":           round(b["signal_count"] * avg_w, 2),
            "industries":         sorted(b["industries"]),
            "personas":           sorted(b["personas"]),
            "source_types":       sorted(b["source_types"]),
            "sample_problems":    b["problems"],
            "sample_outcomes":    b["outcomes"],
            "last_seen":          b["last_seen"].isoformat() if b["last_seen"] else None,
        })

    # Sort by momentum desc
    rows.sort(key=lambda r: r["momentum"], reverse=True)
    return rows[:limit]


@router.get("/demand-signals/detail")
def get_demand_signal_detail(
    label: str = Query(...),
    source_ids: str = Query(default=""),
    days: int = Query(default=180, ge=1, le=730),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return the raw signals that contribute to a given demand signal label."""
    since = datetime.utcnow() - timedelta(days=days)
    q = (
        db.query(Signal)
        .join(Source)
        .filter(
            Signal.demand_signal == label,
            Signal.published_at >= since,
            Source.enabled == 1,
        )
    )

    if source_ids:
        ids = [int(i) for i in source_ids.split(",") if i.strip().isdigit()]
        q = q.filter(Signal.source_id.in_(ids))

    signals = (
        q.order_by(desc(Signal.evidence_weight), desc(Signal.published_at))
        .limit(limit)
        .all()
    )
    return [_signal_to_dict(s) for s in signals]


@router.get("/demand-signals/labels")
def list_demand_signal_labels(db: Session = Depends(get_db)):
    """Return all distinct demand signal labels currently in the DB, sorted."""
    rows = (
        db.query(Signal.demand_signal)
        .filter(Signal.demand_signal.isnot(None), Signal.demand_signal != "")
        .distinct()
        .order_by(Signal.demand_signal)
        .all()
    )
    labels = [r[0] for r in rows]
    def _display(label: str) -> str:
        _ABBREVS = {"ai", "iot", "iiot", "eam", "cmms", "esg", "ot", "it", "roi", "tco", "fm", "hvac"}
        return " ".join(w.upper() if w in _ABBREVS else w.capitalize() for w in label.split("-"))
    return [{"label": l, "display_label": _display(l)} for l in labels]


@router.post("/demand-signals/merge")
def merge_demand_signals(
    source_label: str = Query(..., description="Label to merge FROM (will be removed)"),
    target_label: str = Query(..., description="Label to merge INTO (kept)"),
    db: Session = Depends(get_db),
):
    """
    Reassign all signals with demand_signal == source_label to target_label.
    Use this to collapse near-duplicate labels produced by the LLM.
    """
    if source_label == target_label:
        raise HTTPException(status_code=400, detail="source and target labels must differ")
    updated = (
        db.query(Signal)
        .filter(Signal.demand_signal == source_label)
        .update({"demand_signal": target_label}, synchronize_session=False)
    )
    db.commit()
    return {"merged": updated, "source": source_label, "target": target_label}


# ── Ingestion control ────────────────────────────────────────────────────────

@router.post("/ingest")
def trigger_ingestion(
    background_tasks: BackgroundTasks,
    source_ids: str = Query(default=""),
):
    """
    Manually trigger ingestion then enrichment in the background.
    Phase 1 — fast fetch: all sources scraped and raw signals saved (seconds).
    Phase 2 — async enrich: unenriched signals processed by watsonx.ai (minutes).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ids = [int(i) for i in source_ids.split(",") if i.strip().isdigit()] or None

    def _run():
        global _last_ingestion, _reenrich_status
        started = datetime.utcnow().isoformat()

        _last_ingestion = {"status": "fetching", "started_at": started}
        try:
            result = run_ingestion(source_ids=ids)
            _last_ingestion = {
                "status": "enriching",
                "started_at": started,
                "fetch_finished_at": datetime.utcnow().isoformat(),
                **result,
            }
        except Exception as exc:
            _last_ingestion = {
                "status": "error",
                "phase": "fetch",
                "error": str(exc),
                "finished_at": datetime.utcnow().isoformat(),
            }
            return

        _reenrich_status = {"status": "running", "done": 0, "total": 0, "errors": 0}
        db_session = __import__("app.models", fromlist=["SessionLocal"]).SessionLocal()
        try:
            signals = (
                db_session.query(Signal)
                .filter(Signal.enriched == 0)
                .order_by(Signal.collected_at.desc())
                .limit(5000)
                .all()
            )
            total = len(signals)
            _reenrich_status["total"] = total
            logger.info("Auto-enriching %d new signals after ingest", total)

            work_items = [(s.id, s.title or "", s.body or "") for s in signals]
            done = errors = 0
            results: dict[int, dict] = {}

            def _enrich_one(sig_id, title, body):
                try:
                    return sig_id, enrich_signal(title, body)
                except Exception as exc:
                    logger.warning("Enrichment failed for %d: %s", sig_id, exc)
                    return sig_id, None

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(_enrich_one, sid, t, b): sid
                    for sid, t, b in work_items
                }
                for future in as_completed(futures):
                    sig_id, enrichment = future.result()
                    if enrichment:
                        results[sig_id] = enrichment
                        done += 1
                    else:
                        errors += 1
                    _reenrich_status["done"] = done
                    _reenrich_status["errors"] = errors

            _write_enrichment_results(db_session, signals, results)

            _reenrich_status = {"status": "complete", "done": done, "total": total, "errors": errors}
            _last_ingestion = {
                **_last_ingestion,
                "status": "complete",
                "finished_at": datetime.utcnow().isoformat(),
            }
            logger.info("Ingest+enrich complete: %d enriched, %d errors", done, errors)

        except Exception as exc:
            _reenrich_status = {"status": "error", "error": str(exc)}
            _last_ingestion = {**_last_ingestion, "status": "error", "error": str(exc)}
            logger.error("Auto-enrichment failed: %s", exc)
        finally:
            db_session.close()

    background_tasks.add_task(_run)
    return {"message": "Ingestion started (fetch → enrich pipeline)", "source_ids": ids}


@router.get("/ingest/status")
def ingestion_status():
    return _last_ingestion or {"status": "never_run"}


@router.get("/ingest/debug")
def ingest_debug():
    """Full diagnostic: test RSS fetch + DB write in one call."""
    from app.connectors import fetch_rss, clean_signal
    from app.models import SessionLocal, Signal, Source
    from datetime import datetime

    # 1. Test RSS fetch
    url = "https://news.google.com/rss/search?q=asset+management+maintenance+reliability"
    raw = fetch_rss(url, source_type="trade_media")
    cleaned = [clean_signal(r) for r in raw]
    passed = [s for s in cleaned if len(s.get("body", "").strip()) >= 20]

    # 2. Test DB write — try inserting one dummy signal
    db_error = None
    db_write_ok = False
    try:
        db = SessionLocal()
        test_source = db.query(Source).first()
        if test_source and passed:
            s = passed[0]
            existing = db.query(Signal).filter_by(url=s["url"]).first()
            if existing is None:
                db.add(Signal(
                    source_id=test_source.id,
                    external_id=s.get("external_id", "debug_test"),
                    title=s.get("title", "")[:500],
                    body=s.get("body", ""),
                    url=s["url"][:1000],
                    published_at=s.get("published_at") or datetime.utcnow(),
                    collected_at=datetime.utcnow(),
                    topics=[], sentiment="neutral", relevance_score=0.0,
                    signal_type="general", enriched=0,
                ))
                db.commit()
                db_write_ok = True
            else:
                db_write_ok = "already_exists"
        db.close()
    except Exception as exc:
        db_error = str(exc)

    return {
        "rss_raw": len(raw),
        "rss_passed_filter": len(passed),
        "db_write_ok": db_write_ok,
        "db_error": db_error,
        "sample_title": passed[0]["title"][:80] if passed else None,
        "sample_body_len": len(passed[0].get("body","").strip()) if passed else 0,
    }


_reenrich_status: dict[str, Any] = {}


@router.post("/enrich")
def trigger_reenrichment(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=500, ge=1, le=5000),
    workers: int = Query(default=3, ge=1, le=20),
    unenriched_only: bool = Query(default=False),
):
    """
    Run LLM enrichment on signals using a thread pool.
    unenriched_only=true  → only process signals with enriched=0
    unenriched_only=false → re-process all (useful after prompt upgrades)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _enrich_one(sig_id: int, title: str, body: str):
        try:
            return sig_id, enrich_signal(title, body)
        except Exception as exc:
            logger.warning("Enrichment failed for signal %d: %s", sig_id, exc)
            return sig_id, None

    def _run():
        global _reenrich_status
        _reenrich_status = {"status": "running", "done": 0, "total": 0, "errors": 0}
        db_session = __import__("app.models", fromlist=["SessionLocal"]).SessionLocal()
        try:
            q = db_session.query(Signal)
            if unenriched_only:
                q = q.filter(Signal.enriched == 0)
            # else: re-process all signals (newest first) — no score filter
            signals = (
                q.order_by(desc(Signal.collected_at))
                .limit(limit)
                .all()
            )
            total = len(signals)
            _reenrich_status["total"] = total
            logger.info("Re-enriching %d signals with %d workers", total, workers)

            work_items = [(s.id, s.title or "", s.body or "") for s in signals]
            # Lookup by id so partial batch flushes can resolve Signal ORM objects
            sig_by_id = {s.id: s for s in signals}
            done = errors = 0
            pending: dict[int, dict] = {}   # buffer — flushed every BATCH_SIZE completions

            BATCH_SIZE = 25

            def _flush(batch: dict[int, dict]) -> None:
                """Commit a partial batch so the Demand Signal Radar updates progressively."""
                if not batch:
                    return
                batch_signals = [sig_by_id[sid] for sid in batch if sid in sig_by_id]
                _write_enrichment_results(db_session, batch_signals, batch)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_enrich_one, sig_id, title, body): sig_id
                    for sig_id, title, body in work_items
                }
                for future in as_completed(futures):
                    sig_id, enrichment = future.result()
                    if enrichment:
                        pending[sig_id] = enrichment
                        done += 1
                    else:
                        errors += 1
                    _reenrich_status["done"] = done
                    _reenrich_status["errors"] = errors

                    # Flush to DB every BATCH_SIZE completions so radar updates live
                    if len(pending) >= BATCH_SIZE:
                        _flush(pending)
                        pending = {}

            # Final flush for any remainder
            _flush(pending)
            _reenrich_status = {
                "status": "complete",
                "done": done,
                "total": total,
                "errors": errors,
            }
            logger.info("Re-enrichment done: %d/%d updated, %d errors", done, total, errors)
        except Exception as exc:
            _reenrich_status = {"status": "error", "error": str(exc)}
            logger.error("Re-enrichment run failed: %s", exc)
        finally:
            db_session.close()

    background_tasks.add_task(_run)
    return {
        "message": f"Enrichment started — {workers} parallel workers, up to {limit} signals",
        "unenriched_only": unenriched_only,
    }


@router.get("/enrich/status")
def reenrich_status():
    return _reenrich_status or {"status": "never_run"}


@router.get("/enrich/providers")
def enrich_providers():
    """Return which LLM enrichment providers are configured and their current state."""
    import httpx as _httpx
    from app.enrichment.watsonx import _watsonx_quota_exhausted, _openai_credits_exhausted
    from app.config import settings as cfg

    watsonx_available   = bool(cfg.watsonx_api_key and cfg.watsonx_project_id) and not _watsonx_quota_exhausted
    anthropic_available = bool(cfg.anthropic_api_key)
    openai_available    = bool(cfg.openai_api_key) and not _openai_credits_exhausted

    # Check Ollama reachability (fast probe, don't fail the whole endpoint)
    ollama_reachable = False
    try:
        r = _httpx.get(f"{cfg.ollama_url}/api/tags", timeout=2)
        ollama_reachable = r.status_code == 200
    except Exception:
        pass

    if watsonx_available:
        active = "watsonx"
    elif anthropic_available:
        active = "anthropic"
    elif openai_available:
        active = "openai"
    elif ollama_reachable:
        active = "ollama"
    else:
        active = "keyword_fallback"

    return {
        "active_provider": active,
        "watsonx": {
            "configured": bool(cfg.watsonx_api_key and cfg.watsonx_project_id),
            "quota_exhausted": _watsonx_quota_exhausted,
        },
        "anthropic": {
            "configured": anthropic_available,
            "model": cfg.anthropic_model,
        },
        "openai": {
            "configured": bool(cfg.openai_api_key),
            "credits_exhausted": _openai_credits_exhausted,
        },
        "ollama": {
            "reachable": ollama_reachable,
            "model": cfg.ollama_model,
        },
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_enrichment_results(db_session, signals, results: dict[int, dict]) -> None:
    """Write enrichment results back to DB and rebuild topic summaries."""
    for sig in signals:
        if sig.id in results:
            e = results[sig.id]
            # Original fields
            sig.topics         = e.get("topics", sig.topics)
            sig.sentiment      = e.get("sentiment", sig.sentiment)
            sig.relevance_score = e.get("relevance_score", sig.relevance_score)
            sig.signal_type    = e.get("signal_type", sig.signal_type)
            sig.enriched       = 1
            # New demand-signal fields
            sig.demand_signal   = e.get("demand_signal") or sig.demand_signal
            sig.problem         = e.get("problem") or sig.problem
            sig.desired_outcome = e.get("desired_outcome") or sig.desired_outcome
            sig.approach        = e.get("approach") or sig.approach
            sig.persona         = e.get("persona") or sig.persona
            sig.industry        = e.get("industry") or sig.industry
            sig.org_type        = e.get("org_type") or sig.org_type
            sig.author_type     = e.get("author_type") or sig.author_type
            if e.get("evidence_weight") is not None:
                sig.evidence_weight = e["evidence_weight"]

    db_session.commit()
    rebuild_topic_summaries(db_session)


def _signal_to_dict(s: Signal) -> dict[str, Any]:
    return {
        "id":               s.id,
        "source_id":        s.source_id,
        "source_name":      s.source.name if s.source else "",
        "source_type":      s.source.source_type if s.source else "",
        "title":            s.title,
        "url":              s.url,
        "published_at":     s.published_at.isoformat() if s.published_at else None,
        "collected_at":     s.collected_at.isoformat() if s.collected_at else None,
        # Original enrichment
        "topics":           s.topics or [],
        "sentiment":        s.sentiment,
        "relevance_score":  s.relevance_score,
        "signal_type":      s.signal_type,
        "body_preview":     (s.body or "")[:300],
        # New demand-signal fields
        "demand_signal":    s.demand_signal or "",
        "problem":          s.problem or "",
        "desired_outcome":  s.desired_outcome or "",
        "approach":         s.approach or "",
        "persona":          s.persona or "unknown",
        "industry":         s.industry or "unknown",
        "org_type":         s.org_type or "unknown",
        "author_type":      s.author_type or "unknown",
        "evidence_weight":  s.evidence_weight if s.evidence_weight is not None else 0,
    }


def _sentiment_label(score: float) -> str:
    if score > 0.2:
        return "positive"
    if score < -0.2:
        return "negative"
    return "neutral"
