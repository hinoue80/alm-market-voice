"""
Web crawler connector — uses Tavily to crawl competitor sites and public review pages.
Both source types share the same Tavily crawl mechanism; they differ only in
the instructions passed to focus what content is extracted.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

TAVILY_CRAWL_URL = "https://api.tavily.com/crawl"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"


def fetch_competitor_page(url: str) -> list[dict[str, Any]]:
    """
    Crawl a competitor's product/blog page and extract content signals.
    We do a shallow crawl (depth=1, limit=5) to grab the landing page
    and a handful of linked pages.
    """
    return _tavily_crawl(
        url=url,
        instructions=(
            "Extract product messaging, feature highlights, customer pain points addressed, "
            "use cases, and any market positioning statements. Focus on asset management, "
            "maintenance, sustainability, and EAM content."
        ),
        limit=5,
    )


def fetch_review_page(url: str) -> list[dict[str, Any]]:
    """
    Extract user reviews from public review pages (G2, TrustRadius, Gartner Peer Insights).
    We use extract (single page) rather than crawl to get the review text directly.
    """
    return _tavily_extract(
        url=url,
        instructions=(
            "Extract individual user reviews including the review text, pros, cons, "
            "and any mentioned use cases or pain points. Focus on what users like, "
            "dislike, and wish the product had."
        ),
    )


# ── Internal helpers ─────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _tavily_crawl(url: str, instructions: str, limit: int = 5) -> list[dict[str, Any]]:
    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY not set — skipping crawl for %s", url)
        return []

    results: list[dict[str, Any]] = []
    try:
        resp = httpx.post(
            TAVILY_CRAWL_URL,
            json={
                "url": url,
                "max_depth": 1,
                "limit": limit,
                "instructions": instructions,
                "format": "markdown",
            },
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        pages = resp.json().get("results", [])

        for page in pages:
            content = page.get("content") or page.get("raw_content") or ""
            if len(content.strip()) < 100:
                continue
            results.append({
                "external_id": f"web_{abs(hash(page.get('url', url)))}",
                "title": page.get("title") or _domain(url),
                "body": content[:5000],
                "url": page.get("url", url),
                "published_at": datetime.utcnow(),
                "meta": {"crawled_from": url},
            })

    except Exception as exc:
        logger.error("Tavily crawl failed for %s: %s", url, exc)

    return results


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _tavily_extract(url: str, instructions: str) -> list[dict[str, Any]]:
    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY not set — skipping extract for %s", url)
        return []

    results: list[dict[str, Any]] = []
    try:
        resp = httpx.post(
            TAVILY_EXTRACT_URL,
            json={
                "urls": [url],
                "extract_depth": "advanced",
                "format": "markdown",
                "query": instructions,
            },
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Tavily extract returns results per URL
        for item in data.get("results", []):
            content = item.get("raw_content") or item.get("content") or ""
            if len(content.strip()) < 100:
                continue
            results.append({
                "external_id": f"review_{abs(hash(item.get('url', url)))}",
                "title": item.get("title") or _domain(url),
                "body": content[:5000],
                "url": item.get("url", url),
                "published_at": datetime.utcnow(),
                "meta": {"review_site": _domain(url)},
            })

    except Exception as exc:
        logger.error("Tavily extract failed for %s: %s", url, exc)

    return results


def _domain(url: str) -> str:
    """Extract readable domain name from URL."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url
