"""research_sonar.py — OpenRouter-backed Perplexity Sonar caller (RA-2989).

Wires swarm.research_provider's Perplexity seam to OpenRouter's
`perplexity/sonar` model after Perplexity's direct key was revoked.

The research_provider seam is SYNC — `fn(query: str) -> list[dict]` — so
this is a synchronous httpx call, not the async provider_openrouter.call().

Each returned dict carries title/url/published_date/summary keys.
`_perplexity_records_to_findings` drops any record without a non-empty
title, so the synthesized answer is emitted with the query as its title.

Fails closed (returns []) on missing key, import failure, HTTP error, or
bad JSON, matching the seam's default no-op contract.

Env:
  OPENROUTER_API_KEY       — required; without it this returns [].
  OPENROUTER_SONAR_MODEL   — override model id (default: perplexity/sonar).
  OPENROUTER_HTTP_REFERER  — OpenRouter attribution (default CleanExpo repo).
  OPENROUTER_X_TITLE       — app name (default pi-ceo).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("app.server.research_sonar")

_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT_S = 60.0


def _headers() -> dict[str, str]:
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": os.environ.get(
            "OPENROUTER_HTTP_REFERER", "https://github.com/CleanExpo",
        ),
        "X-Title": os.environ.get("OPENROUTER_X_TITLE", "pi-ceo"),
    }


def _records_from_response(query: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Map an OpenRouter sonar response to research_provider finding dicts."""
    choices = data.get("choices") or []
    answer = ""
    if choices and isinstance(choices[0], dict):
        answer = (choices[0].get("message") or {}).get("content") or ""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records: list[dict[str, Any]] = []

    # Structured search results (newer sonar responses) carry per-source
    # titles — emit one record each so curators see the underlying sources.
    for sr in (data.get("search_results") or []):
        if not isinstance(sr, dict):
            continue
        title = (sr.get("title") or "").strip()
        if not title:
            continue
        records.append({
            "title": title,
            "url": (sr.get("url") or "").strip(),
            "published_date": str(sr.get("date") or today)[:10],
            "summary": (sr.get("snippet") or "").strip(),
        })

    # Always lead with the synthesized answer as a titled record so the
    # finding survives _perplexity_records_to_findings' title filter even
    # when the response only carries a bare `citations` URL list.
    if answer.strip():
        citations = data.get("citations") or []
        primary_url = ""
        if citations and isinstance(citations[0], str):
            primary_url = citations[0]
        records.insert(0, {
            "title": query[:200],
            "url": primary_url,
            "published_date": today,
            "summary": answer,
        })
    return records


def sonar_caller(query: str) -> list[dict[str, Any]]:
    """Query OpenRouter's Perplexity Sonar model for `query`.

    Returns finding dicts (title/url/published_date/summary). Fails closed
    with [] on any error so research_provider degrades gracefully."""
    headers = _headers()
    if not headers:
        log.debug("research_sonar: OPENROUTER_API_KEY missing — empty result")
        return []

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("research_sonar: httpx import failed: %s", exc)
        return []

    body = {
        "model": os.environ.get("OPENROUTER_SONAR_MODEL", "perplexity/sonar"),
        "messages": [{"role": "user", "content": query}],
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=_TIMEOUT_S) as client:
            r = client.post(_OPENROUTER_CHAT_URL, headers=headers, json=body)
    except Exception as exc:  # noqa: BLE001
        log.warning("research_sonar: call raised: %s", exc)
        return []

    if r.status_code >= 400:
        log.warning(
            "research_sonar: http %d: %s", r.status_code, (r.text or "")[:300],
        )
        return []

    try:
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("research_sonar: bad json: %s", exc)
        return []

    records = _records_from_response(query, data)
    log.info("research_sonar: %d record(s) for %r", len(records), query[:80])
    return records


__all__ = ["sonar_caller"]
