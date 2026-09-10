"""
RSS connector — reads analyst blog feeds (Gartner, IDC, Verdantix, ARC Advisory),
community forums, and industry trade media.
Uses feedparser which handles Atom, RSS 1.0, and RSS 2.0.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any
from email.utils import parsedate_to_datetime

import feedparser

logger = logging.getLogger(__name__)

# Keywords that indicate ALM/EAM/ESG relevance — used as a lightweight pre-filter.
# Community and industry_news sources are broader, so we keep this list intentionally wide.
RELEVANCE_KEYWORDS = {
    "asset", "maintenance", "maximo", "envizi", "eam", "cmms", "esg",
    "sustainability", "facility", "facilities", "infrastructure", "iot", "predictive",
    "operational technology", "industrial", "energy", "carbon", "emission",
    "lifecycle", "reliability", "downtime", "ibm", "enterprise asset",
    "utility", "utilities", "plant", "operations", "safety", "compliance",
    "grid", "transmission", "environment", "environmental", "equipment",
    "workforce", "work order", "inspection", "sensor",
}

# Source types where Google News recycles evergreen/old articles.
# Use a longer window so older-but-relevant content isn't silently dropped.
_LOOSE_DATE_TYPES = {"community", "industry_news"}
_STRICT_MAX_AGE_DAYS = 90
_LOOSE_MAX_AGE_DAYS = 365


def fetch_rss(url: str, source_type: str = "rss") -> list[dict[str, Any]]:
    """Parse an RSS/Atom feed and return normalised signal dicts.

    Args:
        url: Feed URL.
        source_type: The Source.source_type value — controls the recency gate.
                     community / industry_news → 365-day window.
                     All others → 90-day window.
    """
    results: list[dict[str, Any]] = []

    max_age = (
        _LOOSE_MAX_AGE_DAYS if source_type in _LOOSE_DATE_TYPES else _STRICT_MAX_AGE_DAYS
    )
    cutoff = datetime.utcnow() - timedelta(days=max_age)

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.warning("RSS feed parse error for %s: %s", url, feed.bozo_exception)
            return results

        for entry in feed.entries[:30]:  # cap at 30 most recent per feed
            title = entry.get("title") or ""
            summary = entry.get("summary") or entry.get("content", [{}])[0].get("value", "")
            link = entry.get("link") or ""

            body = f"{title}. {summary}"

            # Pre-filter: only keep entries with at least one relevance keyword
            body_lower = body.lower()
            if not any(kw in body_lower for kw in RELEVANCE_KEYWORDS):
                continue

            published_at = _parse_date(entry)

            # Recency gate — window depends on source_type
            if published_at < cutoff:
                logger.debug(
                    "Skipping article outside %d-day window (%s): %s",
                    max_age, published_at.date(), title[:60],
                )
                continue

            results.append({
                "external_id": f"rss_{hashlib.sha256(link.encode()).hexdigest()[:16]}",
                "title": title[:500],
                "body": body[:4000],
                "url": link,
                "published_at": published_at,
                "meta": {"feed_title": feed.feed.get("title", "")},
            })

    except Exception as exc:
        logger.error("RSS fetch failed for %s: %s", url, exc)

    return results


def _parse_date(entry: Any) -> datetime:
    """Try multiple date fields; fall back to now."""
    for field in ("published", "updated", "created"):
        raw = entry.get(f"{field}_parsed")
        if raw:
            try:
                import time
                return datetime(*raw[:6])
            except Exception:
                pass
        raw_str = entry.get(field, "")
        if raw_str:
            try:
                return parsedate_to_datetime(raw_str).replace(tzinfo=None)
            except Exception:
                pass
    return datetime.utcnow()
