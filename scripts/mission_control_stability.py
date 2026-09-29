"""AAA check 10 — "Stable": the suite passed on three consecutive scheduled runs.

docs/plans/mission-control/aaa-rating.md check 10: "The full suite has passed on
production on three consecutive scheduled runs (nightly), with zero retries
used." One run cannot see this, so the live workflow downloads the scorecards of
the most recent scheduled runs into a history folder (one sub-folder per run
id), and this module judges each surface over that window.

Consecutive means consecutive: a scheduled run that left no scorecard (cancelled,
secret missing, crashed) breaks the streak exactly as a failing run does. A
re-run (run_attempt > 1) is a retry and does not count. The live Playwright
config pins `retries: 0` (tests/test_mission_control_stability.py guards it), so
a run on attempt 1 used no retries.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = 3


def load_history(folder: Path | None) -> list[dict]:
    """One entry per prior run folder, newest first. No scorecard -> 'missing'."""
    if folder is None or not folder.is_dir():
        return []
    out: list[dict] = []
    for sub in folder.iterdir():
        if not sub.is_dir() or not sub.name.isdigit():
            continue
        card_path = sub / "scorecard.json"
        try:
            card = json.loads(card_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            if card_path.exists():
                print(f"warning: unreadable history {card_path}: {exc}", file=sys.stderr)
            card = None
        out.append({"run_id": int(sub.name), "card": card})
    return sorted(out, key=lambda e: e["run_id"], reverse=True)


def _entry_passed(entry: dict, surface: str) -> tuple[bool, str]:
    card = entry.get("card")
    rid = entry.get("run_id")
    if not card:
        return False, f"run {rid}: no scorecard"
    run = card.get("run") or {}
    if run.get("event") != "schedule":
        return False, f"run {rid}: not a scheduled run"
    if run.get("run_attempt") != 1:
        return False, f"run {rid}: re-run (attempt {run.get('run_attempt')}), a retry"
    row = next((r for r in card.get("surfaces", []) if r.get("surface") == surface), None)
    if not row or row.get("suite_passed") is not True:
        return False, f"run {rid}: suite did not pass for {surface}"
    return True, ""


def judge_stable(surface: str, current: dict | None, history: list[dict]) -> tuple[bool, str]:
    """Met only when the last REQUIRED scheduled runs all passed for <surface>.

    <current> is this run's entry ({"run_id", "card"}); it joins the window only
    when it is itself a scheduled run. A manual run is judged on history alone.
    """
    window: list[dict] = []
    if current and ((current.get("card") or {}).get("run") or {}).get("event") == "schedule":
        window.append(current)
    cur_id = (current or {}).get("run_id")
    window += [e for e in history if e.get("run_id") != cur_id][: REQUIRED - len(window)]
    passed = 0
    for entry in window:
        ok, why = _entry_passed(entry, surface)
        if not ok:
            return False, f"{passed} of {REQUIRED} consecutive scheduled runs passed; {why}"
        passed += 1
    if passed < REQUIRED:
        # Too little history is absence of evidence, not a failure.
        return False, f"not measured: {passed} of {REQUIRED} consecutive scheduled runs recorded"
    return True, ""
