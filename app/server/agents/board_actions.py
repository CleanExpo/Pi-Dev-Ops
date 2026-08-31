"""board_actions.py — turn board-meeting output into machine-actionable artifacts.

Phase 3's free-text SWOT becomes the typed `swarm.intake.spm.SWOT`; Phase 4's
sprint recommendations become Linear tickets instead of dying in markdown;
gap-audit findings become lesson rows so the existing weekly `swarm.meta_curator`
cron (with its Telegram HITL approval) authors the skill — no second approval
surface is built here.

Ticket creation is a real outward action and is OFF by default: the caller must
pass `dry_run=False` **and** set `BOARD_FILE_SPRINT_RECS=1`. Every recommendation
is additionally gated by `check_mandate_consistency`, capped by `BOARD_TICKET_CAP`
(default 3), and routed by projects.json **`id`** — never by `repo`, which is not
unique (`CleanExpo/Pi-Dev-Ops` carries both `pi-dev-ops` and `margot`).
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.server.board_decision_index import build_decision_index, check_mandate_consistency
from swarm.intake.spm import SWOT

log = logging.getLogger("pi-ceo.agents.board-actions")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROJECTS_FILE = _REPO_ROOT / "config" / "harness" / "projects.json"
_MACHINE_SHIP_LABEL = "pi-dev:machine-ship"
_DEFAULT_PROJECT_KEY = "pi-dev-ops"
_DEFAULT_TICKET_CAP = 3
_SPRINT_PRIORITY = 2  # Linear "High"

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_SWOT_HEADS = ("strengths", "weaknesses", "opportunities", "threats")
_SWOT_HEAD_RE = re.compile(
    r"^\s*[#*_\s]*(" + "|".join(_SWOT_HEADS) + r")\b\s*:?\s*[*_]*\s*(.*)$", re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip() == "1"


def _ticket_cap() -> int:
    raw = (os.environ.get("BOARD_TICKET_CAP") or "").strip()
    try:
        return max(0, int(raw)) if raw else _DEFAULT_TICKET_CAP
    except ValueError:
        log.warning("board_actions: bad BOARD_TICKET_CAP=%r — using %d", raw, _DEFAULT_TICKET_CAP)
        return _DEFAULT_TICKET_CAP


def _resolve_routing(project_key: str) -> dict[str, str]:
    """Linear team/project UUIDs for a projects.json `id`. Never keys on `repo`."""
    try:
        data = json.loads(_PROJECTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("board_actions: projects.json unreadable (%s)", exc)
        return {}
    for entry in data.get("projects", []):
        if entry.get("id") != project_key:
            continue
        team = str(entry.get("linear_team_id") or "")
        project = str(entry.get("linear_project_id") or "")
        if team and project:
            return {"team_id": team, "project_id": project}
        log.warning("board_actions: project id=%r has no Linear routing", project_key)
        return {}
    log.warning("board_actions: no projects.json entry with id=%r", project_key)
    return {}


@contextmanager
def _routed(board_meeting: Any, routing: dict[str, str]) -> Iterator[None]:
    """Point board_meeting's Linear helpers at the routed team/project.

    `_linear_create_issue` reads module-level constants rather than taking ids as
    arguments; rebinding them for the call reuses that helper verbatim instead of
    duplicating the mutation. The board meeting is single-threaded batch work.
    """
    previous = (board_meeting._LINEAR_TEAM_ID, board_meeting._LINEAR_PROJECT_ID)
    board_meeting._LINEAR_TEAM_ID = routing["team_id"]
    board_meeting._LINEAR_PROJECT_ID = routing["project_id"]
    try:
        yield
    finally:
        board_meeting._LINEAR_TEAM_ID, board_meeting._LINEAR_PROJECT_ID = previous


def emit_typed_swot(phase3_text: Any) -> SWOT:
    """Parse Phase-3 free text into the typed `swarm.intake.spm.SWOT`.

    Unparseable input yields an empty or partial SWOT — never an exception. A
    board meeting must not die because the model wandered off the format.
    """
    if isinstance(phase3_text, dict):
        phase3_text = phase3_text.get("content", "")
    buckets: dict[str, list[str]] = {head: [] for head in _SWOT_HEADS}
    current = ""
    for line in str(phase3_text or "").splitlines():
        head = _SWOT_HEAD_RE.match(line)
        if head:
            current = head.group(1).lower()
            trailing = head.group(2).strip(" *_:")
            if trailing:
                buckets[current].append(trailing)
            continue
        bullet = _BULLET_RE.match(line)
        if bullet and current:
            buckets[current].append(bullet.group(1).strip(" *_"))
    return SWOT(**{head: buckets[head] for head in _SWOT_HEADS})


def _parse_recommendations(payload: Any) -> list[dict[str, str]]:
    """Strict JSON-block parse. Anything else files NOTHING, by design."""
    text = payload.get("content", "") if isinstance(payload, dict) else str(payload or "")
    match = _JSON_BLOCK_RE.search(str(text))
    if not match:
        log.warning("board_actions: Phase-4 output carries no JSON block — filing nothing")
        return []
    try:
        rows = json.loads(match.group(1))
    except ValueError as exc:
        log.warning("board_actions: Phase-4 JSON block malformed (%s) — filing nothing", exc)
        return []
    if not isinstance(rows, list):
        log.warning("board_actions: Phase-4 JSON block is not a list — filing nothing")
        return []
    parsed: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("ticket") or "").strip()
        rationale = str(row.get("rationale") or "").strip()
        if not title or not rationale:
            continue
        parsed.append({
            "ticket": str(row.get("ticket") or "").strip(), "title": title,
            "rationale": rationale, "estimate": str(row.get("estimate") or "unsized").strip(),
            "impact": str(row.get("impact") or "").strip(),
        })
    return parsed


def _decision_index() -> list[Any] | None:
    """Board decision corpus, or None when it cannot be read (fail closed)."""
    try:
        return build_decision_index()
    except Exception as exc:  # noqa: BLE001 — any failure must block, not approve
        log.warning("board_actions: decision index unavailable (%s) — blocking every rec", exc)
        return None


def _mandate_verdict(rec: dict[str, str], index: list[Any] | None) -> str:
    """Empty string when the recommendation is allowed, else the block reason."""
    if index is None:
        return "board decision corpus unavailable — failing closed"
    mandate = f"{rec['title']} {rec['rationale']} {rec['impact']}"
    try:
        result = check_mandate_consistency(mandate, index)
    except Exception as exc:  # noqa: BLE001 — a broken gate is a closed gate
        return f"mandate check failed: {exc}"
    return "" if result.allowed else result.reason


def _ticket_body(rec: dict[str, str], swot: SWOT | None) -> str:
    lines = [
        "**Sprint priority raised by the board meeting (Phase 4).**", "",
        f"**Rationale:** {rec['rationale']}", f"**Estimate:** {rec['estimate']}",
        f"**Impact:** {rec['impact'] or 'not stated'}",
        f"**Referenced ticket:** {rec['ticket'] or 'none'}",
    ]
    if swot is not None:
        lines += ["", "## SWOT (typed, Phase 3)"] + [
            f"- **{head.title()}:** {'; '.join(getattr(swot, head, []) or []) or 'none recorded'}"
            for head in _SWOT_HEADS
        ]
    lines += ["", f"_Auto-filed by board_actions — {datetime.now(timezone.utc).date().isoformat()}_"]
    return "\n".join(lines)


def _apply_machine_ship_label(board_meeting: Any, identifier: str) -> bool:
    """Best-effort `pi-dev:machine-ship` label. Never raises into the caller."""
    if not _env_flag("BOARD_FILE_MACHINE_SHIP"):
        return False
    from app.server.machine_ship_readiness import machine_ship_readiness

    readiness = machine_ship_readiness()
    if not readiness.get("ready"):
        log.info("board_actions: machine-ship label withheld — %s", readiness.get("blockers"))
        return False
    label_id = board_meeting._get_or_create_label(_MACHINE_SHIP_LABEL)
    if not label_id:
        return False
    return bool(board_meeting._linear_apply_label(identifier, label_id))


def _create_ticket(rec: dict[str, str], swot: SWOT | None, routing: dict[str, str]) -> dict[str, Any]:
    from app.server.agents import board_meeting

    title = rec["title"] if rec["title"].startswith("[SPRINT]") else f"[SPRINT] {rec['title']}"
    try:
        with _routed(board_meeting, routing):
            identifier = board_meeting._linear_create_issue(
                title, _ticket_body(rec, swot), _SPRINT_PRIORITY,
            )
            labelled = _apply_machine_ship_label(board_meeting, identifier)
    except Exception as exc:  # noqa: BLE001 — one bad ticket must not kill the run
        log.warning("board_actions: filing %r failed: %s", title, exc)
        return {"title": title, "action": "error", "reason": str(exc)}
    log.info("board_actions: filed %s (machine_ship=%s)", identifier, labelled)
    return {"title": title, "action": "filed", "identifier": identifier, "machine_ship": labelled}


def file_sprint_recommendations(
    recs: Any,
    *,
    dry_run: bool = True,
    swot: SWOT | None = None,
    project_key: str | None = None,
) -> list[dict[str, Any]]:
    """File Phase-4 sprint recommendations as Linear tickets.

    Default `dry_run=True` returns "would_file" rows and creates nothing. Live
    filing additionally requires `BOARD_FILE_SPRINT_RECS=1`.
    """
    parsed = _parse_recommendations(recs)
    if not parsed:
        return []
    cap = _ticket_cap()
    live = (not dry_run) and _env_flag("BOARD_FILE_SPRINT_RECS")
    routing = _resolve_routing(project_key or os.environ.get("BOARD_PROJECT_KEY") or _DEFAULT_PROJECT_KEY)
    index = _decision_index()
    results: list[dict[str, Any]] = []
    for position, rec in enumerate(parsed):
        base = {"title": rec["title"], "ticket": rec["ticket"]}
        if position >= cap:
            results.append({**base, "action": "capped", "reason": f"BOARD_TICKET_CAP={cap}"})
            continue
        blocked = _mandate_verdict(rec, index)
        if blocked:
            log.warning("board_actions: %r blocked by mandate gate — %s", rec["title"], blocked)
            results.append({**base, "action": "blocked", "reason": blocked})
            continue
        if not live or not routing:
            reason = "dry_run" if not live else "no Linear routing"
            results.append({**base, "action": "would_file", "reason": reason})
            continue
        results.append(_create_ticket(rec, swot, routing))
    return results


def _gap_rows(gaps: Any) -> list[dict[str, Any]]:
    """Flatten a gap-audit result (or a plain list) into lesson rows."""
    items: list[Any] = []
    if isinstance(gaps, dict):
        for severity in ("critical", "high", "low"):
            items += [(severity, g) for g in gaps.get(severity, []) or []]
    elif isinstance(gaps, list):
        items = [("high", g) for g in gaps]
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for severity, gap in items:
        if not isinstance(gap, dict):
            continue
        lesson = str(gap.get("recommendation") or gap.get("reality") or "").strip()
        if not lesson:
            continue
        rows.append({
            "ts": now, "source": "board", "lesson": lesson,
            "category": str(gap.get("category") or "uncategorised").strip(),
            "repo": str(gap.get("repo") or "CleanExpo/Pi-Dev-Ops"),
            "severity": "warn" if severity in ("critical", "high") else "info",
        })
    return rows


def seed_skill_proposals(gaps: Any) -> int:
    """Append board-sourced lesson rows for meta_curator to cluster. Returns the count."""
    rows = _gap_rows(gaps)
    if not rows:
        return 0
    from swarm import meta_curator

    written = 0
    for row in rows:
        try:
            meta_curator._append_jsonl(meta_curator.LESSONS_FILE, row)
            written += 1
        except OSError as exc:
            log.warning("board_actions: lesson append failed (%s)", exc)
    log.info("board_actions: seeded %d board lessons for meta_curator", written)
    return written
