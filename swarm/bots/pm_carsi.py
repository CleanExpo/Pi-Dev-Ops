"""swarm/bots/pm_carsi.py — Senior PM bot for the CARSI cert engine.

Master Plan v3 §5.1.8. CARSI is the cross-vertical certification platform
that issues syllabi + exams + CPD across all six ATIA sub-bodies
(Restoration / Carpet / IEP / Plumbing / HVAC / PressureWashing).

Persona: Rohan Mehta — TPB-registered tax practitioner + 17 years
vocational training delivery in ANZ, ex-TAFE NSW principal trainer,
Cert IV TAE. (Note: same persona name as Duncan's project Tax SME at
~/duncan-work/itr — that's Duncan's repo and an unrelated lane. Here
Rohan is the CARSI cert-lane PM with a distinct context.) Voice:
syllabus-fluent, RTO-compliance-aware, allergic to vibe-coded training.

Cadence:
  * Daily 09:00 AEST general cycle.
  * Weekly Friday 14:00 AEST syllabus-review cycle (longer + deeper).

Output contract:
  * Append one JSONL line to ``.harness/swarm/pm_carsi_state.jsonl``.
  * If a delta is detected, write a markdown briefing to
    ``~/2nd Brain/2nd Brain/Wiki/pm-carsi-daily-briefing-YYYY-MM-DD.md``.
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

log = logging.getLogger("swarm.bots.pm_carsi")

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE_REL = ".harness/swarm/pm_carsi_state.jsonl"
BRIEFING_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
MODEL_ID = "qwen3:14b"
PERSONA_TIMEOUT_S = 600.0
DAILY_HOUR_UTC = 23   # 09:00 AEST = 23:00 UTC
WEEKLY_REVIEW_HOUR_UTC = 4    # 14:00 AEST = 04:00 UTC same day
WEEKLY_REVIEW_WEEKDAY = 4     # Friday (Python weekday(): Mon=0..Sun=6)

CONTEXT_WIKI_PAGES = [
    "carsi.md",
    "industry-association-vision-2026.md",
    "master-plan-2b-by-2028-v3.md",
]


PERSONA_PROMPT = """You are Rohan Mehta, Senior PM-CARSI for Unite-Group's autonomous swarm.

Background: TPB-registered tax practitioner + 17 years vocational training delivery in ANZ. \
Ex-TAFE NSW principal trainer. Cert IV TAE. You know the RTO-compliance backbone, ASQA audit \
flags, the difference between a syllabus and a unit of competency, CPD cycle mechanics, and \
how an exam survives an integrity challenge.

Your lane: CARSI — Certified Australian Restoration & Specialist Industries — the cross-vertical \
LMS. Single platform; vertical-specific cert tracks for Restoration, Carpet, IEP, Plumbing, \
HVAC, PressureWashing. Phill personally authors the first 2 cert syllabi (S500 Water Damage + \
S520 Mould). From cert 3 onward we contract IICRC-credentialled instructors.

Your responsibilities each cycle:
1. Track S500 + S520 syllabus draft state — these are Phill-authored and unblock the entire \
Restoration cohort.
2. Per-vertical cert pathway design (6 verticals × 2-4 certs each).
3. CPD-renewal cadence — a practitioner with 3 certs runs ONE annual renewal cycle, not three.
4. Pricing per cert + instructor-bench utilisation.
5. Cross-vertical reciprocity (e.g. moisture cert valid across Restoration AND IEP).

Weekly Friday review (only on Friday): produce an additional ## Syllabus review section \
covering syllabus draft state, instructor pipeline, and exam-integrity issues.

Escalation rule (to Phill via Telegram with [PM-CARSI] prefix): new cert syllabus approval, \
cross-vertical CPD reciprocity decisions, exam-integrity issues, instructor-bench gaps that \
will block a cert launch within 60 days.

Operating context follows. Read it, then produce today's delta in the exact format below. \
Australian English. No preamble. No filler.

=== CONTEXT (last 7 days of pm_carsi_state + relevant wiki pages) ===
{context_block}
=== END CONTEXT ===

Today's date: {today_iso}
Today is Friday (weekly syllabus review day): {is_friday}

Produce your response in EXACTLY this structure:

## Today's delta
(≤80 words — what materially changed since the last cycle across syllabus drafts + instructor \
pipeline + cert pathway design. If nothing material, say so plainly and stop the response here.)

## Planned next 3 actions
1. (≤25 words)
2. (≤25 words)
3. (≤25 words)

## Escalations to Phill
(One bullet per escalation. Prefix each with [PM-CARSI]. If none, write "None this cycle.")

## Cert pipeline state
(One line per vertical: vertical | live certs | drafting | next launch date.)

{friday_section_hint}

End the response with a single sentinel line on its own:
[PM-CARSI-CYCLE: DELTA] if there is material change today
[PM-CARSI-CYCLE: STEADY] if no material change today
"""

FRIDAY_SECTION_HINT = """## Syllabus review (Friday only)
- S500 Water Damage draft state: (≤30 words)
- S520 Mould draft state: (≤30 words)
- Instructor pipeline (cert 3+): (≤30 words)
- Exam-integrity flags this week: (≤30 words)
"""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _state_path() -> Path:
    return REPO_ROOT / STATE_FILE_REL


def _briefing_path(date_iso: str) -> Path:
    return BRIEFING_DIR / f"pm-carsi-daily-briefing-{date_iso}.md"


def _is_daily_window(now: datetime) -> bool:
    return now.hour == DAILY_HOUR_UTC


def _is_weekly_review_window(now: datetime) -> bool:
    """Friday 14:00 AEST = Friday 04:00 UTC."""
    return now.weekday() == WEEKLY_REVIEW_WEEKDAY and now.hour == WEEKLY_REVIEW_HOUR_UTC


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
    return "[PM-CARSI-CYCLE: DELTA]" in (persona_output or "").upper()


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
        if in_escalations and "[PM-CARSI]" in line:
            out.append(line.strip().lstrip("-•* ").strip())
    return out


def _write_briefing(
    date_iso: str,
    persona_output: str,
    citations: "list | None" = None,
) -> Path:
    """Write the markdown briefing — only called when there's a real delta.

    When ``citations`` is non-empty, append a numbered ``Sources`` block at
    the end using ``format_citations_block`` so each row renders as
    ``[publisher.tld — Headline](url)`` rather than a raw Vertex AI redirect.
    """
    from swarm.research import format_citations_block  # noqa: PLC0415

    p = _briefing_path(date_iso)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"---\ntype: briefing\nowner: PM-CARSI\nupdated: {date_iso}\n---\n\n"
        f"# PM-CARSI daily briefing — {date_iso}\n\n"
        f"Authored by: PM-CARSI (Rohan Mehta persona — CARSI cert lane; distinct from "
        f"Duncan-work tax SME context)\n\n"
        f"{persona_output.strip()}\n"
    )
    sources_block = format_citations_block(
        citations or [], style="markdown", heading="Sources",
    )
    if sources_block:
        body += "\n" + sources_block + "\n"
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
        role="pm.carsi",
        max_tokens=1100,
    )
    return rc, text, err


async def run_pm_carsi(
    session_id: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    citations: "list | None" = None,
) -> dict[str, Any]:
    """One PM-CARSI execution cycle (daily) or weekly syllabus review.

    ``citations`` is an optional list of swarm.research.Citation objects to
    render as a Sources block at the end of the briefing markdown.
    """
    now = _now_utc()
    today_iso = now.strftime("%Y-%m-%d")
    is_friday = now.weekday() == WEEKLY_REVIEW_WEEKDAY

    in_window = _is_daily_window(now) or _is_weekly_review_window(now)
    if not force and not dry_run and not in_window:
        return {
            "persona": "Rohan Mehta / PM-CARSI",
            "status": "skipped",
            "reason": (
                f"outside_windows (utc_hour={now.hour}, weekday={now.weekday()})"
            ),
        }

    recent_state = _read_recent_state(days=7)
    context_block = _read_wiki_context()
    if recent_state:
        context_block += "\n\n### Last 7 days of pm_carsi state rows\n" + json.dumps(
            recent_state[-7:], ensure_ascii=False, indent=2,
        )

    if dry_run:
        row = {
            "ts": now.isoformat(),
            "session_id": session_id or f"dry-run-{today_iso}",
            "persona": "Rohan Mehta / PM-CARSI",
            "mode": "dry_run",
            "delta": False,
            "escalations": [],
            "is_friday_review": is_friday,
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
        is_friday="yes" if is_friday else "no",
        friday_section_hint=FRIDAY_SECTION_HINT if is_friday else "",
    )
    rc, raw_text, err = await _call_persona(prompt)
    if rc != 0 or not raw_text:
        log.warning("PM-CARSI: persona call failed (%s)", err)
        row = {
            "ts": now.isoformat(),
            "session_id": session_id or f"cron-{today_iso}",
            "persona": "Rohan Mehta / PM-CARSI",
            "mode": "live",
            "delta": False,
            "escalations": [],
            "is_friday_review": is_friday,
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
        briefing_path = _write_briefing(today_iso, persona_output, citations=citations)

    row = {
        "ts": now.isoformat(),
        "session_id": session_id or f"cron-{today_iso}",
        "persona": "Rohan Mehta / PM-CARSI",
        "mode": "live",
        "delta": has_delta,
        "escalations": escalations,
        "is_friday_review": is_friday,
        "briefing_path": str(briefing_path) if briefing_path else None,
        "citation_count": len(citations or []),
    }
    _append_state(row)

    return {
        "persona": row["persona"],
        "briefing_path": str(briefing_path) if briefing_path else None,
        "state_jsonl_path": str(_state_path()),
        "escalations": escalations,
        "citation_count": len(citations or []),
        "status": "ok",
    }


def run_cycle(unacked_count: int, *, state: dict | None = None) -> dict:
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        return {"status": "skipped", "reason": "TAO_SWARM_ENABLED!=1"}
    try:
        return asyncio.run(run_pm_carsi(dry_run=False, force=False))
    except Exception as exc:  # noqa: BLE001
        log.warning("PM-CARSI cycle failed: %s", exc)
        return {"status": "error", "error": str(exc)}


__all__ = ["run_pm_carsi", "run_cycle", "PERSONA_PROMPT", "STATE_FILE_REL"]
