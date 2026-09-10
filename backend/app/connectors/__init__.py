"""
Package init for connectors — exposes a single dispatch function.
"""
from app.connectors.reddit import fetch_reddit_json
from app.connectors.rss_reader import fetch_rss
from app.connectors.web_crawler import fetch_competitor_page, fetch_review_page
from app.connectors.noise_filter import clean_signal

__all__ = [
    "fetch_reddit_json",
    "fetch_rss",
    "fetch_competitor_page",
    "fetch_review_page",
    "clean_signal",
]
