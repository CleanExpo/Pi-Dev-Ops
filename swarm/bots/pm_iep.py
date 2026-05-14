"""swarm/bots/pm_iep.py — Senior PM bot for the IEP vertical (NIEPA).

Master Plan v3 §5.1.4. Owns Bulcs Holdings (IAQ Ventilation + AeroAir +
Moisture Meter Experts + Air Purifier) as the wedge, plus the NIEPA
(National Indoor Environmental Professionals Association) sub-body
under ATIA.

Persona: Dr Aria Whitcombe — 15+ years in IAQ and indoor environmental
science. IICRC IEP designation, ex-CSIRO Land & Water research scientist
(particulate exposure modelling). Voice: scientist-rigorous, ASTM-fluent,
allergic to homeopathic mould claims.

Cadence: daily 09:00 AEST.

Output contract:
  * Append one JSONL line to ``.harness/swarm/pm_iep_state.jsonl``.
  * If a delta is detected, write a markdown briefing to
    ``~/2nd Brain/2nd Brain/Wiki/pm-iep-daily-briefing-YYYY-MM-DD.md``.
  * Return a summary dict for the orchestrator audit row.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.bots.pm_iep")

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE_REL = ".harness/swarm/pm_iep_state.jsonl"
BRIEFING_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
MODEL_ID = "qwen3:14b"
PERSONA_TIMEOUT_S = 600.0
DAILY_HOUR_UTC = 23  # 09:00 AEST

CONTEXT_WIKI_PAGES = [
    "bulcs-holdings.md",
    "iaq-building-science-initiative.md",
    "industry-association-vision-2026.md",
    "master-plan-2b-by-2028-v3.md",
]


PERSONA_PROMPT = """You are Dr Aria Whitcombe, Senior PM-IEP for Unite-Group's autonomous swarm.

Background: 15+ years in IAQ and indoor environmental science. IICRC IEP designation. Ex-CSIRO \
Land & Water research scientist — published on particulate exposure modelling and the \
ventilation-rate / mould-growth correlation. You know ASTM D22, the IAQA technical committees, \
moisture-meter physics (pin vs pinless, capacitance vs resistance), and how a building science \
practitioner reads a thermal image. You speak in evidence — no homeopathic mould claims, no \
"toxic mould" tabloid framing.

Your lane:
1. Bulcs Holdings as the IEP wedge — IAQ Ventilation division + AeroAir + Moisture Meter \
Experts + Air Purifier division. Retainer proposal currently in flight (target: signed by \
31 Jul 2026).
2. Cross-reference with Restoration vertical — mould + moisture overlap; Moisture Meter Experts \
is the equipment-commerce bridge to PM-Carpet's commerce flywheel.
3. NIEPA sub-body charter — leverage Bulcs + IAQ Magazine as the wedge. Confirm Ivi Sims as the \
Toby-analogue restoration-vertical co-founder (Ivi sits on IAQA Board / ASTM D22).
4. CARSI IEP cert pathway — S520 Mould + IICRC IEP designation pathway. Cross-vertical CPD \
reciprocity with Restoration (moisture-cert holder valid in both).

Escalation rule (to Phill via Telegram with [PM-IEP] prefix): the Ivi Sims relationship, any \
ASTM / IAQA standards-alignment interaction, sub-body name lock, co-founder candidate \
identification.

Operating context follows. Read it, then produce today's delta in the exact format below. \
Australian English. No preamble. No filler.

=== CONTEXT (last 7 days of pm_iep_state + relevant wiki pages) ===
{context_block}
=== END CONTEXT ===

Today's date: {today_iso}

Produce your response in EXACTLY this structure:

## Today's delta
(≤80 words — what materially changed since the last cycle across Bulcs retainer + NIEPA + IAQ \
Magazine cycle + Moisture Meter commerce overlap. If nothing material, say so plainly and stop \
the response here.)

## Planned next 3 actions
1. (≤25 words)
2. (≤25 words)
3. (≤25 words)

## Escalations to Phill
(One bullet per escalation. Prefix each with [PM-IEP]. If none, write "None this cycle.")

## NIEPA founding cohort state
(One line: members signed | warm pipeline | Bulcs retainer state | by date.)

End the response with a single sentinel line on its own:
[PM-IEP-CYCLE: DELTA] if there is material change today
[PM-IEP-CYCLE: STEADY] if no material change today
"""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _state_path() -> Path:
    return REPO_ROOT / STATE_FILE_REL


def _briefing_path(date_iso: str) -> Path:
    return BRIEFING_DIR / f"pm-iep-daily-briefing-{date_iso}.md"


def _read_recent_state(days: int = 7) -> list[dict[str, Any]]:
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
    return "[PM-IEP-CYCLE: DELTA]" in (persona_output or "").upper()


def _extract_escalations(persona_output: str) -> list[str]:
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
        if in_escalations and "[PM-IEP]" in line:
            out.append(line.strip().lstrip("-•* ").strip())
    return out


def _write_briefing(date_iso: str, persona_output: str) -> Path:
    p = _briefing_path(date_iso)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"---\ntype: briefing\nowner: PM-IEP\nupdated: {date_iso}\n---\n\n"
        f"# PM-IEP daily briefing — {date_iso}\n\n"
        f"Authored by: PM-IEP (Dr Aria Whitcombe persona)\n\n"
        f"{persona_output.strip()}\n"
    )
    p.write_text(body, encoding="utf-8")
    return p


def _strip_think_tags(text: str) -> str:
    out = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


async def _call_persona(prompt: str) -> tuple[int, str, str | None]:
    from app.server.provider_ollama import call as ollama_call  # noqa: PLC0415

    rc, text, _cost, err = await ollama_call(
        prompt=prompt,
        model_id=MODEL_ID,
        timeout_s=PERSONA_TIMEOUT_S,
        role="pm.iep",
        max_tokens=900,
    )
    return rc, text, err


async def run_pm_iep(
    session_id: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """One PM-IEP execution cycle."""
    now = _now_utc()
    today_iso = now.strftime("%Y-%m-%d")

    if not force and not dry_run:
        if now.hour != DAILY_HOUR_UTC:
            return {
                "persona": "Dr Aria Whitcombe / PM-IEP",
                "status": "skipped",
                "reason": f"outside_daily_window (utc_hour={now.hour})",
            }

    recent_state = _read_recent_state(days=7)
    context_block = _read_wiki_context()
    if recent_state:
        context_block += "\n\n### Last 7 days of pm_iep state rows\n" + json.dumps(
            recent_state[-7:], ensure_ascii=False, indent=2,
        )

    if dry_run:
        row = {
            "ts": now.isoformat(),
            "session_id": session_id or f"dry-run-{today_iso}",
            "persona": "Dr Aria Whitcombe / PM-IEP",
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

    prompt = PERSONA_PROMPT.format(context_block=context_block, today_iso=today_iso)
    rc, raw_text, err = await _call_persona(prompt)
    if rc != 0 or not raw_text:
        log.warning("PM-IEP: persona call failed (%s)", err)
        row = {
            "ts": now.isoformat(),
            "session_id": session_id or f"cron-{today_iso}",
            "persona": "Dr Aria Whitcombe / PM-IEP",
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
        "persona": "Dr Aria Whitcombe / PM-IEP",
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
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        return {"status": "skipped", "reason": "TAO_SWARM_ENABLED!=1"}
    try:
        return asyncio.run(run_pm_iep(dry_run=False, force=False))
    except Exception as exc:  # noqa: BLE001
        log.warning("PM-IEP cycle failed: %s", exc)
        return {"status": "error", "error": str(exc)}


__all__ = ["run_pm_iep", "run_cycle", "PERSONA_PROMPT", "STATE_FILE_REL"]
