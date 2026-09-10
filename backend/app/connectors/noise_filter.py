"""
Content noise filter — strips boilerplate from scraped web content before enrichment.

Removes:
  - Cookie / GDPR consent banners
  - Navigation menus and footer link lists
  - "Subscribe to newsletter" / marketing opt-in blocks
  - Generic legal disclaimers and privacy policy blurbs
  - Repetitive UI chrome (breadcrumbs, share buttons, tag lists)
  - Short sentences that carry no signal (< 8 words)

Preserves the substantive body text (product descriptions, reviews, posts, articles).
"""
from __future__ import annotations

import re

# ── Regex patterns compiled once at module load ────────────────────────────────

# Multi-line blocks that start with cookie/GDPR noise
_COOKIE_BLOCK = re.compile(
    r"(we use cookies|this (site|website) uses cookies|by (clicking|continuing|using)|"
    r"cookie (policy|settings|preferences)|accept (all )?cookies|"
    r"your privacy|privacy (settings|choices|preference)|"
    r"gdpr|california (privacy|consumer)|ccpa|do not sell my)",
    re.IGNORECASE,
)

# Navigation / footer boilerplate lines (single nav item OR pipe-separated nav list)
_NAV_LINE = re.compile(
    r"^(home|about( us)?|contact( us)?|careers|login|sign (in|up)|get (started|a demo)|"
    r"resources|blog|newsroom|press|investors|partners|support|help( center)?|"
    r"privacy policy|terms (of (service|use))?|cookie policy|sitemap|"
    r"follow us|share (this|on)|subscribe|newsletter|©|\(c\)|all rights reserved)\s*$",
    re.IGNORECASE,
)

# Pipe-separated nav lists (e.g. "Home | About | Contact | Login")
_NAV_PIPE_LIST = re.compile(
    r"^(\s*(home|about|contact|login|sign (in|up)|careers|resources|blog|support|"
    r"privacy|terms|sitemap|partners)\s*\|){2,}",
    re.IGNORECASE,
)

# Social / share noise
_SOCIAL_NOISE = re.compile(
    r"(share on (twitter|linkedin|facebook|email)|tweet this|"
    r"click to (share|tweet)|copy link|copied!)",
    re.IGNORECASE,
)

# Tag / category label lines (e.g. "Tags: cloud, iot, maintenance")
_TAG_LINE = re.compile(
    r"^(tags?|categories|category|topics?|labels?)\s*:?\s*",
    re.IGNORECASE,
)

# Repetitive call-to-action sentences
_CTA = re.compile(
    r"(request (a )?(demo|trial|quote)|schedule (a )?(demo|call)|"
    r"talk to (an )?expert|contact (sales|us)|get (a )?free|"
    r"download (the )?(whitepaper|report|ebook|guide)|learn more →|"
    r"read (the )?(full|more)|see all (posts|articles|resources))",
    re.IGNORECASE,
)

# Lines that are just a URL
_URL_ONLY = re.compile(r"^\s*https?://\S+\s*$")

# Markdown link cleanup: [text](url) → text
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")

# Markdown image cleanup: ![alt](url) → ''
_MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]+\)")

# Excessive whitespace
_MULTI_BLANK = re.compile(r"\n{3,}")


def clean(text: str, min_line_words: int = 4) -> str:
    """
    Clean scraped text by removing noise and boilerplate.

    Args:
        text: Raw scraped / markdown text from a web page.
        min_line_words: Lines with fewer words than this are dropped (default 4).

    Returns:
        Cleaned text string. May be significantly shorter than input.
    """
    if not text:
        return ""

    # Remove markdown images first (no signal)
    text = _MD_IMG.sub("", text)

    # Convert markdown links to plain text
    text = _MD_LINK.sub(r"\1", text)

    lines = text.splitlines()
    kept: list[str] = []
    skip_block = False

    for raw_line in lines:
        line = raw_line.strip()

        # ── Block-level noise: once we hit a cookie/GDPR trigger, skip until blank line ──
        if _COOKIE_BLOCK.search(line):
            skip_block = True
        if skip_block:
            if not line:
                skip_block = False  # blank line ends the noisy block
            continue

        # ── Line-level noise ──
        if not line:
            kept.append("")  # preserve paragraph breaks
            continue
        if _NAV_LINE.match(line):
            continue
        if _NAV_PIPE_LIST.match(line):
            continue
        if _SOCIAL_NOISE.search(line):
            continue
        if _TAG_LINE.match(line):
            continue
        if _CTA.search(line):
            continue
        if _URL_ONLY.match(line):
            continue

        # Drop very short lines — these are usually nav items, button labels, etc.
        word_count = len(line.split())
        if word_count < min_line_words:
            continue

        kept.append(line)

    cleaned = "\n".join(kept)

    # Collapse 3+ blank lines down to 2
    cleaned = _MULTI_BLANK.sub("\n\n", cleaned)

    return cleaned.strip()


def clean_signal(signal: dict) -> dict:
    """
    Apply noise filtering to a raw signal dict in-place (modifies 'body').
    Returns the same dict (for chaining).
    """
    signal["body"] = clean(signal.get("body", ""))
    # Also clean the title of any markdown link syntax
    signal["title"] = _MD_LINK.sub(r"\1", signal.get("title", "")).strip()
    return signal
