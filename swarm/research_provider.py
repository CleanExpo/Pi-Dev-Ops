"""swarm/research_provider.py — RA-2027 (HERMES Wave 1).

NotebookLM-first SCAN provider with Perplexity fallback. Implements the
research-routing layer for the Discovery loop's Protocol 1 (SCAN).

Operator decision 2026-05-06:
  Use NotebookLM (already connected, free) as the first-line research
  source. Fall back to Perplexity only when NotebookLM lacks the
  signal. Most Discovery watch-list queries are portfolio-internal
  (NRPG pricing, DR-NRPG accreditation, CCW client model) — NotebookLM
  grounds them better. Perplexity stays for genuinely external signals
  (regulator updates, competitor announcements, market data).

Cost discipline:
  * NotebookLM: $0 (already connected, no per-query cost)
  * Perplexity: ≤$5/day hard cap (tracked in ~/.hermes/perplexity-ledger.json)

Public API:
    research(query, *, persona_id, prefer_external=False) -> list[Finding]

When `prefer_external=True`, the caller has flagged this as a market /
regulator / competitor signal — skip NotebookLM and go straight to
Perplexity.

Hooks:
  This module exposes `set_notebooklm_caller(fn)` and
  `set_perplexity_caller(fn)` so tests + dev environments can swap the
  underlying transports. Production wiring happens in `app_factory.py`
  startup.

The returned list[Finding] flows directly into Discovery's existing
Protocol 1 hash-dedup / Gemma 4 summarisation / GAP classification.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.server.discovery import Finding

log = logging.getLogger("pi-ceo.research_provider")

# ── Persona → NotebookLM notebook mapping ────────────────────────────────────

# Operator-provisioned notebooks. Mapping discovered via `nlm notebook list`
# 2026-05-06. The notebooks named "Pi-CEO — <persona> Knowledge Base" are
# the canonical Discovery surfaces; other notebooks are background corpus.
_DEFAULT_NOTEBOOK_MAP: dict[str, str] = {
    "restoreassist": "Pi-CEO — RestoreAssist Knowledge Base",
    "synthex": "Pi-CEO — Synthex Knowledge Base",
    # CleanExpo is the umbrella for RestoreAssist + DR-NRPG; serve as a
    # secondary knowledge base for those personas via override.
    "cleanexpo": "Pi-CEO — CleanExpo Knowledge Base",
}


def _load_notebook_map() -> dict[str, str]:
    """Read persona→notebook overrides from
    ~/.hermes/discovery-notebooks.json if present, else use defaults.

    Schema: {"<persona_id>": "<notebook_name_or_id>", ...}
    """
    cfg_path = Path(os.environ.get(
        "HERMES_ROOT", str(Path.home() / ".hermes")
    )) / "discovery-notebooks.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**_DEFAULT_NOTEBOOK_MAP, **data}
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("research_provider: %s load failed (%s) — defaults", cfg_path, exc)
    return dict(_DEFAULT_NOTEBOOK_MAP)


# ── Perplexity ledger for $5/day cap ─────────────────────────────────────────


_PERPLEXITY_LEDGER_PATH = Path(os.environ.get(
    "HERMES_ROOT", str(Path.home() / ".hermes")
)) / "perplexity-ledger.json"

# Per-call USD estimate. Sonar Pro charges ~$5/1M tokens. Average watch-list
# query produces ~3K tokens (1K prompt + 2K completion). 0.015 USD per call
# is a conservative estimate; real billing reconciliation lands in Phase 5.
PERPLEXITY_USD_PER_CALL: float = 0.015
PERPLEXITY_DAILY_CAP_USD: float = float(
    os.environ.get("DISCOVERY_PERPLEXITY_DAILY_CAP_USD", "5.0")
)


def _ledger_today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_ledger() -> dict[str, Any]:
    if not _PERPLEXITY_LEDGER_PATH.exists():
        return {"version": 1, "spend": {}}
    try:
        return json.loads(_PERPLEXITY_LEDGER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "spend": {}}


def _save_ledger(ledger: dict[str, Any]) -> None:
    _PERPLEXITY_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PERPLEXITY_LEDGER_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(_PERPLEXITY_LEDGER_PATH))


def _perplexity_budget_remaining_usd() -> float:
    """Returns USD remaining today. Negative when over cap (caller stops)."""
    ledger = _load_ledger()
    today_spend = float(ledger.get("spend", {}).get(_ledger_today_key(), 0.0))
    return PERPLEXITY_DAILY_CAP_USD - today_spend


def _record_perplexity_spend(usd: float) -> None:
    ledger = _load_ledger()
    spend = ledger.setdefault("spend", {})
    today = _ledger_today_key()
    spend[today] = float(spend.get(today, 0.0)) + float(usd)
    _save_ledger(ledger)


# ── NotebookLM transport ─────────────────────────────────────────────────────


def _default_notebooklm_caller(notebook_name: str, query: str) -> str:
    """Default transport — shell out to `nlm cross query`. Returns the
    notebook's text answer or "" on any error."""
    try:
        proc = subprocess.run(
            ["nlm", "cross", "query", query, "--notebooks", notebook_name],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as exc:
        log.warning("research_provider: nlm subprocess failed (%s)", exc)
        return ""
    if proc.returncode != 0:
        log.warning(
            "research_provider: nlm rc=%d stderr=%s",
            proc.returncode, (proc.stderr or "")[:200],
        )
        return ""
    return (proc.stdout or "").strip()


_NOTEBOOKLM_CALLER: Any = _default_notebooklm_caller


def set_notebooklm_caller(fn) -> None:
    """Override the NotebookLM transport. Tests inject a mock; production
    can swap to an MCP-based caller when one ships."""
    global _NOTEBOOKLM_CALLER  # noqa: PLW0603
    _NOTEBOOKLM_CALLER = fn


# ── Perplexity transport ─────────────────────────────────────────────────────


def _default_perplexity_caller(query: str) -> list[dict[str, Any]]:
    """Default transport — would call `mcp__pi-ceo__perplexity_research`.
    Production wiring lives in app_factory.py startup; this default
    returns [] so the system fails closed when wiring is missing."""
    log.debug("research_provider: no perplexity caller registered — empty result")
    return []


_PERPLEXITY_CALLER: Any = _default_perplexity_caller


def set_perplexity_caller(fn) -> None:
    """Register the Perplexity transport.
    Shape: `fn(query: str) -> list[dict]` where each dict is a finding
    with title/url/published_date/summary keys."""
    global _PERPLEXITY_CALLER  # noqa: PLW0603
    _PERPLEXITY_CALLER = fn


# ── NotebookLM result → Finding parsing ──────────────────────────────────────


def _looks_like_no_signal(answer: str) -> bool:
    """Heuristic: NotebookLM returns canned 'I don't have specific
    information' phrasing when the corpus lacks the answer. Detect that
    so we know to fall through to Perplexity.

    Conservative — only counts as "no signal" when the entire answer is
    one of these phrases. A long answer that happens to include "I don't
    have" inside doesn't trigger the fallback.
    """
    s = answer.strip().lower()
    if not s:
        return True
    no_signal_phrases = (
        "i don't have",
        "i do not have",
        "the sources don't",
        "the sources do not",
        "no relevant information",
        "not enough context",
        "unknown",
    )
    if len(s) < 280:
        for phrase in no_signal_phrases:
            if phrase in s:
                return True
    return False


def _notebooklm_answer_to_finding(
    answer: str, *, persona_id: str, query: str, notebook_name: str,
) -> Finding | None:
    """Convert a NotebookLM cross-query answer into a single Finding.
    Returns None when the answer is empty or looks like a no-signal."""
    if _looks_like_no_signal(answer):
        return None
    # Title is the query itself (concise, scannable in Linear). The full
    # NotebookLM answer becomes the summary. URL is the notebook deep-link
    # so curators can verify source.
    return Finding(
        persona_id=persona_id,
        title=f"[corpus] {query}"[:200],
        url=f"notebooklm://{notebook_name}",
        published_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        summary=answer[:4000],  # bound payload size; full answer in jsonl report
        source="notebooklm",
        raw_query=query,
    )


def _perplexity_records_to_findings(
    records: list[dict[str, Any]], *, persona_id: str, query: str,
) -> list[Finding]:
    """Convert raw Perplexity records to Findings."""
    out: list[Finding] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        if not title:
            continue
        out.append(Finding(
            persona_id=persona_id,
            title=title[:200],
            url=url,
            published_date=str(r.get("published_date") or "")[:10],
            summary=(r.get("summary") or r.get("snippet") or "")[:4000],
            source="perplexity",
            raw_query=query,
        ))
    return out


# ── Public API ───────────────────────────────────────────────────────────────


def research(
    query: str,
    *,
    persona_id: str,
    prefer_external: bool = False,
) -> list[Finding]:
    """NotebookLM-first research with Perplexity fallback. Returns
    list[Finding] for Discovery's SCAN protocol.

    Routing logic:
      1. If `prefer_external=True`, skip NotebookLM (caller signaled
         this is an external/market signal). Go straight to Perplexity.
      2. Else: ask NotebookLM. If it returns a real answer, return one
         Finding sourced from the notebook.
      3. If NotebookLM returns no-signal AND Perplexity budget remains,
         call Perplexity. Returns list[Finding] sourced from Perplexity.
      4. If Perplexity budget exhausted, return [] and log the
         budget-exceeded condition.
    """
    if not (query or "").strip():
        return []

    # Step 1: external-signal shortcut
    if prefer_external:
        return _call_perplexity(query, persona_id)

    # Step 2: NotebookLM first
    notebook_map = _load_notebook_map()
    notebook = notebook_map.get(persona_id)
    if notebook:
        try:
            answer = _NOTEBOOKLM_CALLER(notebook, query)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "research_provider: notebooklm call raised for %s: %s",
                persona_id, exc,
            )
            answer = ""
        finding = _notebooklm_answer_to_finding(
            answer, persona_id=persona_id, query=query, notebook_name=notebook,
        )
        if finding is not None:
            return [finding]
        log.debug(
            "research_provider: notebooklm no-signal for %s/%r — falling back",
            persona_id, query,
        )

    # Step 3: Perplexity fallback
    return _call_perplexity(query, persona_id)


def _call_perplexity(query: str, persona_id: str) -> list[Finding]:
    """Cap-aware Perplexity call. Returns [] when budget exhausted."""
    remaining = _perplexity_budget_remaining_usd()
    if remaining < PERPLEXITY_USD_PER_CALL:
        log.info(
            "research_provider: perplexity budget exhausted ($%.2f remaining < $%.3f) — skipping",
            remaining, PERPLEXITY_USD_PER_CALL,
        )
        return []
    try:
        records = _PERPLEXITY_CALLER(query)
    except Exception as exc:  # noqa: BLE001
        log.warning("research_provider: perplexity call raised: %s", exc)
        return []
    _record_perplexity_spend(PERPLEXITY_USD_PER_CALL)
    return _perplexity_records_to_findings(
        records or [], persona_id=persona_id, query=query,
    )


__all__ = [
    "PERPLEXITY_DAILY_CAP_USD",
    "PERPLEXITY_USD_PER_CALL",
    "research",
    "set_notebooklm_caller",
    "set_perplexity_caller",
]
