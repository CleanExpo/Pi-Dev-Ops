"""swarm/bots/pm_atia.py — Senior PM bot for the ATIA meta-association.

Master Plan v3 §5.1.1. Owns the umbrella brand that sits above the six
vertical sub-bodies (Restoration / Carpet / IEP / Plumbing / HVAC /
PressureWashing) plus CARSI as the cross-vertical cert engine.

Persona: Catriona Walsh — 15+ years ANZ trade-association leadership,
ex-Master Builders Association NSW policy chief, COSBOA-network veteran.
Voice: institutional, regulator-fluent, allergic to vanity governance.

Cadence: daily 09:00 AEST (= 23:00 UTC the prior day; UTC hour 23).
Trigger: also fires on ATIA brand-identity / insurance-partner /
sub-body-charter / conference-keynote events surfaced via Linear.

Output contract:
  * Append one JSONL line to ``.harness/swarm/pm_atia_state.jsonl``.
  * If a delta is detected, write a markdown briefing to
    ``~/2nd Brain/2nd Brain/Wiki/atia-daily-briefing-YYYY-MM-DD.md``.
  * Return a summary dict for the orchestrator audit row.

Scaffold-only: ``run_pm_atia`` is wired but the LLM call path is gated
behind ``force=True`` so Phill validates the first real cycle. Default
behaviour writes a no-LLM "scaffold-cycle" JSONL row so the contract holds.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.bots.pm_atia")

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE_REL = ".harness/swarm/pm_atia_state.jsonl"
BRIEFING_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
MODEL_ID = "qwen3:14b"
PERSONA_TIMEOUT_S = 600.0
DAILY_HOUR_UTC = 23  # 09:00 AEST = 23:00 UTC prior day (UTC+10 standard)

# Wiki pages the PM reads each cycle (always-on context).
CONTEXT_WIKI_PAGES = [
    "industry-association-vision-2026.md",
    "master-plan-2b-by-2028-v3.md",
    "restoration-industry-context.md",
]


PERSONA_PROMPT = """You are Catriona Walsh, Senior PM-ATIA for Unite-Group's autonomous swarm.

Background: 15+ years in ANZ trade-association leadership. Ex-Master Builders Association NSW \
policy chief. You know how COSBOA networks form, how insurance partners (Allianz / Suncorp / IAG \
/ AAMI / Youi) negotiate group schemes, and how an industry body wins recognition without paid \
ads. You are institutional, regulator-fluent, and allergic to vanity governance.

Your lane: the Australian Trade Industry Association (ATIA) — the umbrella brand that sits above \
six vertical sub-bodies (NRPG Restoration, CCPA Carpet, NIEPA IEP, NPPA Plumbing, NHPA HVAC, \
NPWPA Pressure Washing) and CARSI as the cross-vertical certification engine.

Your responsibilities each cycle:
1. Track ATIA brand registration progress (domain lock, IP Australia trademark filing, designer \
brief, masthead).
2. Cross-vertical standards harmonisation — what one sub-body publishes that needs reciprocity \
to another.
3. Insurance-partner pipeline (target 3 MoUs of 5 majors by 30 Jun 2027).
4. Conference planning — inaugural ATIA conference Q3 2027, target 500 attendees + 8 sponsors.
5. Sub-body chartering cadence — which charter is ratifiable this fortnight.

You DO NOT do the verticals' work. You harmonise across them and own the meta brand.

Escalation rule (route to Phill via Telegram with [ATIA] prefix): any insurance-partner \
first-meeting, conference keynote slot, legal entity decision, trademark filing, or sub-body \
charter ratification.

Operating context follows. Read it, then produce today's delta in the exact format below. \
Australian English. No preamble. No filler.

=== CONTEXT (last 7 days of pm_atia_state + relevant wiki pages) ===
{context_block}
=== END CONTEXT ===

Today's date: {today_iso}

Produce your response in EXACTLY this structure:

## Today's delta
(≤80 words — what materially changed since the last cycle. If nothing material, say so plainly \
and stop the response here.)

## Planned next 3 actions
1. (≤25 words)
2. (≤25 words)
3. (≤25 words)

## Escalations to Phill
(One bullet per escalation requiring his voice. Prefix each with [ATIA]. If none, write \
"None this cycle.")

## Insurance-partner pipeline state
(One line per active partner: name | stage | next move | by date.)

End the response with a single sentinel line on its own:
[ATIA-CYCLE: DELTA] if there is material change today
[ATIA-CYCLE: STEADY] if no material change today
"""


# ── State / context helpers ─────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _state_path() -> Path:
    return REPO_ROOT / STATE_FILE_REL


def _briefing_path(date_iso: str) -> Path:
    return BRIEFING_DIR / f"atia-daily-briefing-{date_iso}.md"


def _read_recent_state(days: int = 7) -> list[dict[str, Any]]:
    """Load the last N days of pm_atia_state rows. Empty list if file missing."""
    p = _state_path()
    if not p.exists():
        return []
    cutoff = _now_utc() - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts_raw = row.get("ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except Exception:
            continue
        if ts >= cutoff:
            out.append(row)
    return out


def _read_wiki_context(max_chars_per_page: int = 4000) -> str:
    """Concatenate the canonical wiki pages this PM reads each cycle."""
    wiki_root = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
    chunks: list[str] = []
    for name in CONTEXT_WIKI_PAGES:
        p = wiki_root / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")[:max_chars_per_page]
        except Exception:
            continue
        chunks.append(f"### {name}\n{text}")
    return "\n\n".join(chunks) if chunks else "(no wiki context available)"


def _append_state(row: dict[str, Any]) -> Path:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


def _has_material_delta(persona_output: str) -> bool:
    """Look for the [ATIA-CYCLE: DELTA] sentinel."""
    return "[ATIA-CYCLE: DELTA]" in (persona_output or "").upper()


def _extract_escalations(persona_output: str) -> list[str]:
    """Pull lines tagged [ATIA] from the escalations section."""
    if not persona_output:
        return []
    out: list[str] = []
    in_escalations = False
    for line in persona_output.splitlines():
        if line.strip().startswith("## Escalations"):
            in_escalations = True
            continue
        if line.strip().startswith("## "):
            in_escalations = False
        if in_escalations and "[ATIA]" in line:
            out.append(line.strip().lstrip("-•* ").strip())
    return out


def _write_briefing(date_iso: str, persona_output: str) -> Path:
    """Write the markdown briefing — only called when there's a real delta."""
    p = _briefing_path(date_iso)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"---\ntype: briefing\nowner: PM-ATIA\nupdated: {date_iso}\n---\n\n"
        f"# ATIA daily briefing — {date_iso}\n\n"
        f"Authored by: PM-ATIA (Catriona Walsh persona)\n\n"
        f"{persona_output.strip()}\n"
    )
    p.write_text(body, encoding="utf-8")
    return p


# ── LLM call ─────────────────────────────────────────────────────────────────


async def _call_persona(prompt: str) -> tuple[int, str, str | None]:
    """Wrap the Ollama call with this PM's timeout and role tag."""
    from app.server.provider_ollama import call as ollama_call  # noqa: PLC0415

    rc, text, _cost, err = await ollama_call(
        prompt=prompt,
        model_id=MODEL_ID,
        timeout_s=PERSONA_TIMEOUT_S,
        role="pm.atia",
        max_tokens=900,
    )
    return rc, text, err


def _strip_think_tags(text: str) -> str:
    import re

    out = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# ── Public entry ─────────────────────────────────────────────────────────────


async def run_pm_atia(
    session_id: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """One PM-ATIA execution cycle.

    Args:
        session_id: optional trigger id (Linear ticket or cron tick).
        force: ignore the daily-hour window guard.
        dry_run: skip the LLM call; write a scaffold-cycle JSONL row only.

    Returns a summary dict the orchestrator can audit.
    """
    now = _now_utc()
    today_iso = now.strftime("%Y-%m-%d")

    # Cadence guard — fire once per day at the configured UTC hour, unless forced.
    if not force and not dry_run:
        if now.hour != DAILY_HOUR_UTC:
            return {
                "persona": "Catriona Walsh / PM-ATIA",
                "status": "skipped",
                "reason": f"outside_daily_window (utc_hour={now.hour})",
            }

    recent_state = _read_recent_state(days=7)
    context_block = _read_wiki_context()
    if recent_state:
        context_block += "\n\n### Last 7 days of pm_atia state rows\n" + json.dumps(
            recent_state[-7:], ensure_ascii=False, indent=2,
        )

    if dry_run:
        row = {
            "ts": now.isoformat(),
            "session_id": session_id or f"dry-run-{today_iso}",
            "persona": "Catriona Walsh / PM-ATIA",
            "mode": "dry_run",
            "delta": False,
            "escalations": [],
        }
        state_path = _append_state(row)
        return {
            "persona": row["persona"],
            "briefing_path": None,
            "state_jsonl_path": str(state_path),
            "escalations": [],
            "status": "ok_dry_run",
        }

    prompt = PERSONA_PROMPT.format(
        context_block=context_block,
        today_iso=today_iso,
    )

    rc, raw_text, err = await _call_persona(prompt)
    if rc != 0 or not raw_text:
        log.warning("PM-ATIA: persona call failed (%s)", err)
        row = {
            "ts": now.isoformat(),
            "session_id": session_id or f"cron-{today_iso}",
            "persona": "Catriona Walsh / PM-ATIA",
            "mode": "live",
            "delta": False,
            "escalations": [],
            "error": err or "unknown",
        }
        _append_state(row)
        return {
            "persona": row["persona"],
            "briefing_path": None,
            "state_jsonl_path": str(_state_path()),
            "escalations": [],
            "status": "llm_failed",
            "error": err,
        }

    persona_output = _strip_think_tags(raw_text)
    has_delta = _has_material_delta(persona_output)
    escalations = _extract_escalations(persona_output)

    briefing_path: Path | None = None
    if has_delta:
        briefing_path = _write_briefing(today_iso, persona_output)

    row = {
        "ts": now.isoformat(),
        "session_id": session_id or f"cron-{today_iso}",
        "persona": "Catriona Walsh / PM-ATIA",
        "mode": "live",
        "delta": has_delta,
        "escalations": escalations,
        "briefing_path": str(briefing_path) if briefing_path else None,
    }
    _append_state(row)

    return {
        "persona": row["persona"],
        "briefing_path": str(briefing_path) if briefing_path else None,
        "state_jsonl_path": str(_state_path()),
        "escalations": escalations,
        "status": "ok",
    }


def run_cycle(unacked_count: int, *, state: dict | None = None) -> dict:
    """Sync entry point for orchestrator. Wraps the async run.

    Self-gates on TAO_SWARM_ENABLED; never raises.
    """
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        return {"status": "skipped", "reason": "TAO_SWARM_ENABLED!=1"}
    try:
        return asyncio.run(run_pm_atia(dry_run=False, force=False))
    except Exception as exc:  # noqa: BLE001 — never crash the loop
        log.warning("PM-ATIA cycle failed: %s", exc)
        return {"status": "error", "error": str(exc)}


__all__ = ["run_pm_atia", "run_cycle", "PERSONA_PROMPT", "STATE_FILE_REL"]
