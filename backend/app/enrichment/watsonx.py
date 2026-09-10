"""
Enrichment module — extracts demand signals from practitioner content.

Provider priority:
  1. watsonx.ai  (meta-llama/llama-3-3-70b-instruct) — primary; skipped when
                 rate-limited (consumption_limit_reached), retries up to 3×
  2. Anthropic   (claude-haiku-4-5) — skipped if ANTHROPIC_API_KEY is blank
  3. OpenAI      (gpt-4o-mini)      — skipped if OPENAI_API_KEY is blank
  4. Ollama      (llama3.2 local)   — always-available free fallback on Apple Silicon
  5. Keyword     — offline fallback when Ollama is unreachable

Output schema:
  demand_signal    : 4-8 word kebab-case pattern name
  problem          : what the practitioner is struggling with
  desired_outcome  : business/operational result they want
  approach         : what they're trying or asking about
  persona          : role/title inferred
  industry         : sector (Manufacturing, Utilities, Facilities, etc.)
  org_type         : asset_owner | vendor | consultant | unknown
  author_type      : practitioner | vendor | unknown
  evidence_weight  : 0–5
  topics           : array of 3-6 specific topic strings
  sentiment        : positive | negative | neutral
  relevance_score  : 0.0–1.0
  signal_type      : demand | complaint | analyst | general
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ── IAM token cache (watsonx.ai) ─────────────────────────────────────────────
_iam_token: str = ""
_iam_token_expires_at: float = 0.0
_IAM_REFRESH_BUFFER_SECS = 300


def _get_iam_token() -> str:
    global _iam_token, _iam_token_expires_at
    if _iam_token and time.time() < _iam_token_expires_at:
        return _iam_token
    try:
        resp = httpx.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": settings.watsonx_api_key,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        _iam_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        _iam_token_expires_at = time.time() + expires_in - _IAM_REFRESH_BUFFER_SECS
        logger.debug("IAM token refreshed; expires in %ds", expires_in)
        return _iam_token
    except Exception as exc:
        logger.error("Failed to get IAM token: %s", exc)
        return ""


# ── Shared prompt ─────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """\
You are a market intelligence analyst for IBM's Asset Lifecycle Management (ALM) portfolio \
(IBM Maximo — EAM/CMMS for physical assets, maintenance, and reliability).

Your job: extract practitioner demand signals from the content below. \
Focus purely on physical asset management, maintenance, reliability, facilities, \
and field service. Ignore anything about IT assets, software development, ESG/sustainability, \
or vendor marketing.

Return a single JSON object with EXACTLY these keys:

"demand_signal": A 4-8 word kebab-case label naming the core demand pattern.
  Examples: "reactive-to-planned-maintenance-transition", "unplanned-downtime-reduction",
  "mobile-workforce-field-service", "spare-parts-inventory-optimisation",
  "predictive-maintenance-roi-justification", "legacy-cmms-cloud-migration-blockers",
  "ot-it-integration-complexity", "real-time-asset-health-monitoring"

"problem": One sentence — what the practitioner is struggling with right now. \
  Grounded in their words. Empty string if not determinable.

"desired_outcome": One sentence — the operational or business result they want. \
  Empty string if not determinable.

"approach": One sentence — what they are trying, asking about, or evaluating. \
  Empty string if not determinable.

"persona": The likely role/title of the author or subject (e.g. "Maintenance Manager", \
  "Reliability Engineer", "Facilities Director", "Plant Manager"). \
  "unknown" if not determinable.

"industry": The most likely industry sector. Choose from: \
  Manufacturing, Utilities, Facilities, Oil & Gas, Transportation, \
  Healthcare, Government, Mining, General. "unknown" if not determinable.

"org_type": One of "asset_owner", "vendor", "consultant", "unknown". \
  Use "asset_owner" for practitioners who operate and maintain physical assets. \
  Use "vendor" for software/technology providers. Use "consultant" for advisory firms.

"author_type": One of "practitioner", "vendor", "unknown". \
  "practitioner" = person who operates/maintains physical assets (highest value). \
  "vendor" = content written to promote a product/service.

"evidence_weight": Integer 0-5. Score how strongly this represents a genuine practitioner demand signal:
  5 = Practitioner asking peers a real operational problem
  4 = Practitioner-led conference session or abstract
  3 = Practitioner-written case study or article
  2 = Analyst/trade media covering practitioner pain points
  1 = Practitioner + vendor co-presentation or sponsored content
  0 = Vendor-only/promotional (no practitioner voice)

"topics": Array of 3-6 SHORT specific topic strings (3-6 words each). \
  Be SPECIFIC: "AI-driven work order prioritisation", not "asset management". \
  Use language practitioners use, not marketing jargon.

"sentiment": One of "positive", "negative", "neutral" (practitioner's attitude toward the problem/solution).

"relevance_score": Float 0.0-1.0. How relevant is this to IBM Maximo buyers? \
  1.0 = directly about EAM/CMMS/maintenance/asset management \
  0.5 = adjacent (facilities, field service, OT/IT) \
  0.0 = irrelevant (IT assets, software dev, ESG, vendor promo)

"signal_type": One of "demand", "complaint", "analyst", "general". \
  "demand" = practitioner expressing a need or want \
  "complaint" = practitioner expressing frustration or failure \
  "analyst" = analyst/research firm perspective \
  "general" = informational, no clear demand signal

Return ONLY valid JSON. No explanation. No markdown fences. No extra text.

Content:
\"\"\"
{text}
\"\"\"

JSON:
"""


# ── watsonx.ai provider ───────────────────────────────────────────────────────
# Tracks whether the current watsonx session has hit its token quota.
# Reset at startup; set to True on first 403 quota error so we stop trying.
_watsonx_quota_exhausted: bool = False


def _call_watsonx(text: str) -> dict[str, Any] | None:
    """
    Call watsonx.ai. Returns parsed enrichment dict or None on any error.
    Sets _watsonx_quota_exhausted=True on token_quota_reached so callers
    can immediately route to the OpenAI fallback.
    """
    global _watsonx_quota_exhausted

    if _watsonx_quota_exhausted:
        return None
    if not settings.watsonx_api_key or not settings.watsonx_project_id:
        return None

    for attempt in range(3):
        try:
            token = _get_iam_token()
            if not token:
                return None

            prompt = PROMPT_TEMPLATE.format(text=text)
            resp = httpx.post(
                f"{settings.watsonx_url}/ml/v1/text/generation?version=2023-05-29",
                json={
                    "model_id": "meta-llama/llama-3-3-70b-instruct",
                    "input": prompt,
                    "parameters": {
                        "max_new_tokens": 400,
                        "temperature": 0.1,
                        "stop_sequences": ["###", "\n\n\n"],
                    },
                    "project_id": settings.watsonx_project_id,
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if resp.status_code == 429:
                # Check if this is a hard quota exhaustion or just a rate limit
                try:
                    body_429 = resp.json()
                    errors_429 = body_429.get("errors", [])
                    if any(e.get("code") == "token_quota_reached" for e in errors_429):
                        logger.warning("watsonx.ai token quota exhausted — switching to fallback")
                        _watsonx_quota_exhausted = True
                        return None
                except Exception:
                    pass
                # Transient rate limit (consumption_limit_reached, concurrent cap) — wait and retry
                retry_after = int(resp.headers.get("Retry-After", "10"))
                wait = retry_after + attempt * 5
                logger.debug("watsonx.ai 429 rate-limit — waiting %ds (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                body = resp.json()
                errors = body.get("errors", [])
                if any(e.get("code") == "token_quota_reached" for e in errors):
                    logger.warning(
                        "watsonx.ai token quota exhausted — switching to fallback"
                    )
                    _watsonx_quota_exhausted = True
                    return None
                # Other 403 (project access, etc.)
                logger.warning("watsonx.ai 403: %s", body)
                return None

            resp.raise_for_status()
            raw = resp.json()["results"][0]["generated_text"].strip()
            return _parse_response(raw)

        except Exception as exc:
            if attempt == 0 and "429" in str(exc):
                time.sleep(5)
                continue
            logger.warning("watsonx.ai call failed: %s", exc)
            return None

    return None


# ── OpenAI provider ───────────────────────────────────────────────────────────

# Set to True on first credit_balance_exhausted so we skip all future calls.
_openai_credits_exhausted: bool = False


def _call_openai(text: str) -> dict[str, Any] | None:
    """
    Call OpenAI gpt-4o-mini with the same prompt + JSON schema.
    Returns parsed enrichment dict or None on any error.
    """
    global _openai_credits_exhausted

    if not settings.openai_api_key:
        logger.debug("OpenAI API key not configured — skipping OpenAI fallback")
        return None
    if _openai_credits_exhausted:
        return None

    prompt = PROMPT_TEMPLATE.format(text=text)

    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a JSON-only responder. "
                            "Output a single valid JSON object and nothing else."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            },
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if resp.status_code == 429:
            # Distinguish credit exhaustion from rate limiting
            try:
                err = resp.json().get("error", {})
                if err.get("code") == "credit_balance_exhausted":
                    logger.warning("OpenAI credits exhausted — skipping OpenAI for this session, using Ollama")
                    _openai_credits_exhausted = True
                    return None
            except Exception:
                pass
            logger.warning("OpenAI rate limit hit — skipping")
            return None

        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        result = _parse_response(raw)
        logger.debug("OpenAI enrichment succeeded for signal")
        return result

    except Exception as exc:
        logger.warning("OpenAI enrichment failed: %s", exc)
        return None



# ── Anthropic provider ───────────────────────────────────────────────────────

def _call_anthropic(text: str) -> dict[str, Any] | None:
    """
    Call Anthropic claude-haiku-4-5 (or model from config).
    Returns parsed enrichment dict or None on any error.
    Fast (~1-2s), high quality, low cost (~$0.001/signal).
    """
    if not settings.anthropic_api_key:
        return None

    # Build a concise system + user message pair
    system = (
        "You are a JSON-only market intelligence analyst. "
        "Output a single valid JSON object and nothing else. "
        "No markdown fences, no explanation."
    )

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": settings.anthropic_model,
                "max_tokens": 600,
                "temperature": 0.1,
                "system": system,
                "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(text=text)}],
            },
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=30,
        )

        if resp.status_code == 401:
            logger.warning("Anthropic API key invalid — skipping Anthropic for this session")
            # Blank the key so we don't keep trying
            settings.anthropic_api_key = ""
            return None

        if resp.status_code == 429:
            logger.warning("Anthropic rate limit — falling through to next provider")
            return None

        resp.raise_for_status()
        content = resp.json()["content"][0]["text"].strip()
        result = _parse_response(content)
        logger.debug("Anthropic enrichment succeeded")
        return result

    except Exception as exc:
        logger.warning("Anthropic enrichment failed: %s", exc)
        return None


# ── Ollama provider ───────────────────────────────────────────────────────────

def _call_ollama(text: str) -> dict[str, Any] | None:
    """
    Call local Ollama with llama3.2 in JSON mode.
    Returns parsed enrichment dict or None on any error.
    No quota, no cost — runs entirely on device.
    """
    try:
        # Quick reachability check
        probe = httpx.get(f"{settings.ollama_url}/api/tags", timeout=3)
        if probe.status_code != 200:
            logger.debug("Ollama not reachable — skipping")
            return None
    except Exception:
        logger.debug("Ollama not reachable — skipping")
        return None

    prompt = PROMPT_TEMPLATE.format(text=text)

    try:
        resp = httpx.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model":  settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1, "num_predict": 500},
            },
            timeout=120,  # local inference can take a moment on first cold run
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        result = _parse_response(raw)
        logger.debug("Ollama enrichment succeeded")
        return result

    except Exception as exc:
        logger.warning("Ollama enrichment failed: %s", exc)
        return None



# ── Public entry point ────────────────────────────────────────────────────────

def enrich_signal(title: str, body: str) -> dict[str, Any]:
    """
    Enrich a signal using the best available provider:
      1. watsonx.ai  — primary (skipped if quota exhausted this session)
      2. Anthropic   — fast, high quality (skipped if key blank/invalid)
      3. OpenAI      — fallback when watsonx quota is hit
      4. Ollama      — local free fallback (llama3.2, no quota)
      5. Keyword     — always-available offline fallback
    """
    text = f"{title}\n\n{body}"[:2500]

    # 1. Try watsonx.ai
    result = _call_watsonx(text)
    if result is not None:
        return result

    # 2. Try Anthropic
    result = _call_anthropic(text)
    if result is not None:
        return result

    # 3. Try OpenAI
    result = _call_openai(text)
    if result is not None:
        return result

    # 4. Try Ollama (local)
    result = _call_ollama(text)
    if result is not None:
        return result

    # 5. Keyword fallback
    logger.debug("All LLM providers unavailable — using keyword fallback")
    return _fallback_enrichment(title, body)


# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_response(raw: str) -> dict[str, Any]:
    """Extract JSON from model output, tolerating minor formatting issues."""
    raw = re.sub(r"```json\s*|```\s*", "", raw).strip()

    start = raw.find("{")
    if start == -1:
        return _default_enrichment()

    depth = 0
    end = -1
    for i, ch in enumerate(raw[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        return _default_enrichment()

    try:
        data = json.loads(raw[start:end])
        return {
            "demand_signal":   _safe_str(data.get("demand_signal"), 200),
            "problem":         _safe_str(data.get("problem"), 2000),
            "desired_outcome": _safe_str(data.get("desired_outcome"), 2000),
            "approach":        _safe_str(data.get("approach"), 2000),
            "persona":         _safe_str(data.get("persona"), 200),
            "industry":        _safe_str(data.get("industry"), 100),
            "org_type":        _safe_enum(data.get("org_type"), {"asset_owner", "vendor", "consultant", "unknown"}, "unknown"),
            "author_type":     _safe_enum(data.get("author_type"), {"practitioner", "vendor", "unknown"}, "unknown"),
            "evidence_weight": _safe_int(data.get("evidence_weight"), 0, 5, 0),
            "topics":          _safe_list(data.get("topics"), 6),
            "sentiment":       _safe_enum(data.get("sentiment"), {"positive", "negative", "neutral"}, "neutral"),
            "relevance_score": _safe_float(data.get("relevance_score"), 0.5),
            "signal_type":     _safe_enum(data.get("signal_type"), {"demand", "complaint", "analyst", "general"}, "general"),
        }
    except json.JSONDecodeError:
        return _default_enrichment()


# ── Keyword fallback ──────────────────────────────────────────────────────────

def _fallback_enrichment(title: str, body: str) -> dict[str, Any]:
    """Simple keyword-based fallback when all LLM providers are unavailable."""
    text = (title + " " + body).lower()

    TOPIC_KEYWORDS: dict[str, list[str]] = {
        "predictive maintenance": ["predictive", "prediction", "forecast", "anomaly"],
        "CMMS migration":         ["migration", "upgrade", "legacy", "modernize", "transition"],
        "asset management":       ["asset", "eam", "maximo", "lifecycle", "infrastructure"],
        "IoT / sensors":          ["iot", "sensor", "connected", "telemetry", "real-time"],
        "compliance":             ["compliance", "regulatory", "audit", "iso", "regulation"],
        "cost reduction":         ["cost", "savings", "efficiency", "roi", "budget"],
        "downtime reduction":     ["downtime", "uptime", "reliability", "availability", "mtbf"],
        "work order management":  ["work order", "work orders", "workorder", "maintenance request"],
    }
    topics = [t for t, kws in TOPIC_KEYWORDS.items() if any(k in text for k in kws)][:5]

    sentiment = "neutral"
    if any(w in text for w in ["great", "excellent", "love", "best", "improve"]):
        sentiment = "positive"
    elif any(w in text for w in ["bad", "issue", "problem", "fail", "broken", "slow", "struggle"]):
        sentiment = "negative"

    relevance_score = min(1.0, 0.3 + len(topics) * 0.15)

    signal_type = "general"
    if any(w in text for w in ["need", "want", "wish", "looking for", "require"]):
        signal_type = "demand"
    elif any(w in text for w in ["issue", "problem", "fail", "broken", "hate"]):
        signal_type = "complaint"
    elif any(w in text for w in ["report", "analyst", "gartner", "idc", "verdantix", "arc"]):
        signal_type = "analyst"

    return {
        "demand_signal":   "",
        "problem":         "",
        "desired_outcome": "",
        "approach":        "",
        "persona":         "unknown",
        "industry":        "unknown",
        "org_type":        "unknown",
        "author_type":     "unknown",
        "evidence_weight": 0,
        "topics":          topics if topics else ["asset management"],
        "sentiment":       sentiment,
        "relevance_score": relevance_score,
        "signal_type":     signal_type,
    }


def _default_enrichment() -> dict[str, Any]:
    return {
        "demand_signal":   "",
        "problem":         "",
        "desired_outcome": "",
        "approach":        "",
        "persona":         "unknown",
        "industry":        "unknown",
        "org_type":        "unknown",
        "author_type":     "unknown",
        "evidence_weight": 0,
        "topics":          [],
        "sentiment":       "neutral",
        "relevance_score": 0.3,
        "signal_type":     "general",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_str(val: Any, max_len: int) -> str:
    if isinstance(val, str):
        return val[:max_len].strip()
    return ""


def _safe_list(val: Any, max_len: int) -> list[str]:
    if isinstance(val, list):
        return [str(v)[:100] for v in val[:max_len]]
    return []


def _safe_enum(val: Any, allowed: set, default: str) -> str:
    return val if val in allowed else default


def _safe_float(val: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(val)))
    except (TypeError, ValueError):
        return default
