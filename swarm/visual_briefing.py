"""swarm/visual_briefing.py — 4x daily visual briefings via NotebookLM + Telegram.

Produces rich briefings at 06:00, 12:00, 18:00, 22:00 AEST:
  06:00 — Morning brief: overnight activity, Board decisions, day priorities
  12:00 — Midday pulse: health status, active fixes, top Linear movement
  18:00 — Evening research: tech drops, enhancement proposals, new intelligence
  22:00 — Night summary: what shipped, Board directives issued, tomorrow's queue

Each briefing:
  1. Assembles text from: 6-pager, Board minutes, fix_jobs, wiki updates
  2. Creates/updates a NotebookLM notebook with the briefing content
  3. Generates an audio overview (podcast-style) + optional video
  4. Downloads the audio file
  5. Sends to Phill via Telegram (audio + text summary)

Public API:
    should_fire(slot, state) -> bool      # slot: "morning"|"midday"|"evening"|"night"
    run_briefing(slot, repo_root) -> BriefingResult
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.visual_briefing")

REPO_ROOT = Path(__file__).resolve().parents[1]

# AEST = UTC+10. Slots fire within the first cycle after these UTC hours.
SLOTS: dict[str, int] = {
    "morning": 20,   # 06:00 AEST = 20:00 UTC (prev day)
    "midday":   2,   # 12:00 AEST = 02:00 UTC
    "evening":  8,   # 18:00 AEST = 08:00 UTC
    "night":   12,   # 22:00 AEST = 12:00 UTC
}

SLOT_LABELS = {
    "morning": "Morning Brief — Overnight + Day Priorities",
    "midday":  "Midday Pulse — Health + Active Fixes",
    "evening": "Evening Intel — Tech Drops + Enhancements",
    "night":   "Night Summary — What Shipped + Tomorrow",
}

NLM_NOTEBOOK_PREFIX = "Pi-CEO Daily Brief"


@dataclass
class BriefingResult:
    slot: str
    text_brief: str = ""
    audio_path: str = ""
    notebook_id: str = ""
    telegram_sent: bool = False
    error: str | None = None


def should_fire(slot: str, state: dict) -> bool:
    """True if this slot hasn't fired today within ±30 min of its scheduled hour."""
    key = f"last_briefing_{slot}"
    last = state.get(key)
    now_utc = datetime.now(timezone.utc)
    target_hour = SLOTS.get(slot, 0)

    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            # Don't re-fire within 23 hours
            if (now_utc - last_dt).total_seconds() < 23 * 3600:
                return False
        except (ValueError, TypeError):
            pass

    return now_utc.hour == target_hour


def _assemble_brief(slot: str) -> str:
    """Assemble text content for the briefing from all available sources."""
    sections: list[str] = [f"# {SLOT_LABELS[slot]}\n**{datetime.now().strftime('%A %d %B %Y, %I:%M %p AEST')}**\n"]

    # 6-pager (assembled by the daily briefing system)
    try:
        from . import six_pager  # noqa: PLC0415
        brief = six_pager.assemble_six_pager(repo_root=REPO_ROOT)
        if brief:
            sections.append(f"## Portfolio Health\n{brief[:2000]}")
    except Exception as exc:  # noqa: BLE001
        log.debug("visual_briefing: six_pager failed (%s)", exc)

    # Recent Board minutes
    try:
        minutes_dir = REPO_ROOT / ".harness" / "board" / "minutes"
        if minutes_dir.exists():
            recent = sorted(minutes_dir.glob("*.md"))[-3:]
            for p in recent:
                sections.append(f"## Board: {p.stem}\n{p.read_text()[:800]}")
    except Exception as exc:  # noqa: BLE001
        log.debug("visual_briefing: board minutes failed (%s)", exc)

    # Active fix jobs
    try:
        fix_log = REPO_ROOT / ".harness" / "swarm" / "fix_jobs.jsonl"
        if fix_log.exists():
            jobs: dict[str, Any] = {}
            for line in fix_log.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    jobs[row.get("job_id", "")] = row
            active = [j for j in jobs.values() if j.get("status") not in ("done", "failed")]
            if active:
                job_lines = "\n".join(
                    f"- {j['project_id']} | {j['failure_type']} | {j['status']} "
                    f"({'✅ PR: ' + j['pr_url'] if j.get('pr_url') else '🔧 fixing'})"
                    for j in active[:10]
                )
                sections.append(f"## Active Fix Jobs ({len(active)})\n{job_lines}")
    except Exception as exc:  # noqa: BLE001
        log.debug("visual_briefing: fix_jobs failed (%s)", exc)

    # Evening slot: add wiki tech-drops + enhancement proposals
    if slot == "evening":
        try:
            wiki = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
            drops = wiki / "tech-drops-q2-2026.md"
            if drops.exists():
                sections.append(f"## Latest Tech Drops\n{drops.read_text()[:1500]}")
        except Exception as exc:  # noqa: BLE001
            log.debug("visual_briefing: tech-drops failed (%s)", exc)

    return "\n\n".join(sections)


def _nlm_create_or_update_notebook(slot: str, content: str) -> str:
    """Create or update a NotebookLM notebook with the briefing content. Returns notebook ID."""
    try:
        # Write content to a temp file as a text source
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                         prefix=f"pi-ceo-brief-{slot}-",
                                         delete=False) as f:
            f.write(content)
            tmp_path = f.name

        notebook_title = f"{NLM_NOTEBOOK_PREFIX} — {slot.title()}"

        # Create notebook with the briefing as a source
        result = subprocess.run(
            ["nlm", "notebook", "create", "--title", notebook_title,
             "--source", tmp_path],
            capture_output=True, text=True, timeout=60,
        )
        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode == 0:
            # Extract notebook ID from output
            import re  # noqa: PLC0415
            m = re.search(r'[a-f0-9-]{36}', result.stdout)
            return m.group() if m else ""
        log.warning("visual_briefing: nlm create failed — %s", result.stderr[:200])
    except Exception as exc:  # noqa: BLE001
        log.warning("visual_briefing: nlm notebook create raised (%s)", exc)
    return ""


def _nlm_generate_audio(notebook_id: str) -> str:
    """Generate audio overview for the notebook. Returns path to audio file."""
    if not notebook_id:
        return ""
    try:
        result = subprocess.run(
            ["nlm", "audio", "create", notebook_id],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.warning("visual_briefing: nlm audio create failed — %s", result.stderr[:200])
            return ""

        # Download the audio
        out_dir = REPO_ROOT / ".harness" / "briefings"
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_filename = f"brief-{datetime.now().strftime('%Y%m%d-%H%M')}.mp3"
        audio_path = str(out_dir / audio_filename)

        dl = subprocess.run(
            ["nlm", "download", notebook_id, "--output", audio_path],
            capture_output=True, text=True, timeout=120,
        )
        if dl.returncode == 0 and Path(audio_path).exists():
            return audio_path
        log.warning("visual_briefing: nlm download failed — %s", dl.stderr[:200])
    except Exception as exc:  # noqa: BLE001
        log.warning("visual_briefing: nlm audio pipeline raised (%s)", exc)
    return ""


def _send_telegram(text: str, audio_path: str = "") -> bool:
    """Send briefing text + optional audio to Phill via Telegram."""
    try:
        from . import telegram_alerts  # noqa: PLC0415
        sender = getattr(telegram_alerts, "send", None)
        if not callable(sender):
            return False
        kwargs: dict[str, Any] = {"severity": "info", "bot_name": "Margot"}
        if audio_path and Path(audio_path).exists():
            kwargs["audio_path"] = audio_path
        sender(text, **kwargs)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("visual_briefing: telegram send failed (%s)", exc)
        return False


def run_briefing(slot: str, repo_root: Path | None = None) -> BriefingResult:
    """Assemble and deliver one briefing slot."""
    result = BriefingResult(slot=slot)

    # 1. Assemble text
    result.text_brief = _assemble_brief(slot)

    # 2. Create NotebookLM notebook + generate audio
    result.notebook_id = _nlm_create_or_update_notebook(slot, result.text_brief)
    if result.notebook_id:
        result.audio_path = _nlm_generate_audio(result.notebook_id)

    # 3. Build Telegram message
    label = SLOT_LABELS.get(slot, slot.title())
    telegram_text = (
        f"📊 **{label}**\n\n"
        f"{result.text_brief[:600]}...\n\n"
        + ("🎧 Audio briefing attached." if result.audio_path else "")
    )

    # 4. Send
    result.telegram_sent = _send_telegram(telegram_text, result.audio_path)
    log.info("visual_briefing: %s sent — audio=%s telegram=%s",
             slot, bool(result.audio_path), result.telegram_sent)

    return result


__all__ = ["run_briefing", "should_fire", "BriefingResult", "SLOTS"]
