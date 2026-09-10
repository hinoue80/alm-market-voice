"""
Reddit connector — uses Reddit's public JSON API (no auth needed for read-only).
Falls back to Tavily search if the JSON endpoint is rate-limited.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "ALMMarketVoice/1.0 (internal IBM tool; contact alm-marketing@ibm.com)"
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def fetch_reddit_json(url: str) -> list[dict[str, Any]]:
    """
    Fetch top posts from a subreddit using Reddit's public JSON endpoint.
    URL should be: https://www.reddit.com/r/<sub>/top/.json?t=week&limit=25
    """
    results: list[dict[str, Any]] = []

    try:
        response = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        response.raise_for_status()
        data = response.json()

        posts = data.get("data", {}).get("children", [])
        for post in posts:
            p = post.get("data", {})
            if p.get("is_self") is False and not p.get("selftext"):
                # Link post with no body — skip or use title only
                body = p.get("title", "")
            else:
                body = p.get("selftext") or p.get("title") or ""

            if not body.strip():
                continue

            # Parse subreddit name from URL for display
            subreddit = p.get("subreddit_name_prefixed", "r/unknown")

            results.append({
                "external_id": f"reddit_{p.get('id', '')}",
                "title": p.get("title", "")[:500],
                "body": body[:4000],
                "url": f"https://www.reddit.com{p.get('permalink', '')}",
                "published_at": _ts(p.get("created_utc")),
                "meta": {"subreddit": subreddit, "score": p.get("score", 0)},
            })

    except Exception as exc:
        logger.warning("Reddit JSON fetch failed for %s: %s — trying Tavily fallback", url, exc)
        results = _tavily_fallback(url)

    return results


def _tavily_fallback(reddit_url: str) -> list[dict[str, Any]]:
    """
    Fallback: use Tavily *search* (not crawl) to find recent Reddit discussions.
    Search is ~2-3s vs ~20s for a crawl, and Reddit 403s don't block it.
    """
    if not settings.tavily_api_key:
        return []

    # Extract subreddit name from URL: .../r/<sub>/top/.json → "r/<sub>"
    import re
    m = re.search(r"/r/([^/]+)", reddit_url)
    subreddit = m.group(1) if m else "maximo"

    # Build a targeted search query
    query = f"site:reddit.com/r/{subreddit} asset management maintenance"

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "query": query,
                "max_results": 5,
                "search_depth": "basic",
                "include_answer": False,
            },
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("results", [])
        results = []
        for item in items:
            content = item.get("content") or ""
            if len(content) < 50:
                continue
            results.append({
                "external_id": f"reddit_tavily_{hashlib.sha256((item.get('url') or '').encode()).hexdigest()[:16]}",
                "title": item.get("title") or "Reddit post",
                "body": content[:4000],
                "url": item.get("url", ""),
                "published_at": datetime.utcnow(),
                "meta": {"subreddit": f"r/{subreddit}", "score": 0},
            })
        return results
    except Exception as exc:
        logger.error("Tavily Reddit fallback also failed: %s", exc)
        return []


def _ts(epoch: float | None) -> datetime:
    if epoch:
        return datetime.utcfromtimestamp(float(epoch))
    return datetime.utcnow()
