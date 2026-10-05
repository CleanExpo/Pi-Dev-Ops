"""AAA check 10: three consecutive scheduled runs, zero retries.

The rules that stop the grade flattering itself: too little history is not
met, a scheduled run with no scorecard breaks the streak, a re-run is a retry,
a manual run never counts toward the three, and one failing night resets it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import mission_control_scorecard as sc
from scripts import mission_control_stability as st

ROOT = Path(__file__).resolve().parents[1]


def _card(passed: bool, event: str = "schedule", attempt: int = 1, surface: str = "MC-13") -> dict:
    return {"run": {"event": event, "run_attempt": attempt},
            "surfaces": [{"surface": surface, "suite_passed": passed}]}


def _history(tmp_path: Path, cards: dict[int, dict | None]) -> list[dict]:
    for rid, card in cards.items():
        (tmp_path / str(rid)).mkdir()
        if card is not None:
            (tmp_path / str(rid) / "scorecard.json").write_text(json.dumps(card), encoding="utf-8")
    return st.load_history(tmp_path)


def _current(passed: bool, event: str = "schedule", attempt: int = 1) -> dict:
    return {"run_id": 900, "card": _card(passed, event, attempt)}


def test_three_passing_scheduled_runs_meet_check_ten(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: _card(True), 700: _card(True)})
    assert st.judge_stable("MC-13", _current(True), hist) == (True, "")


def test_too_little_history_is_not_measured_rather_than_failed(tmp_path: Path) -> None:
    met, why = st.judge_stable("MC-13", _current(True), _history(tmp_path, {800: _card(True)}))
    assert not met
    assert why.startswith("not measured: 2 of 3")


def test_a_scheduled_run_with_no_scorecard_breaks_the_streak(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: None, 700: _card(True), 600: _card(True)})
    met, why = st.judge_stable("MC-13", _current(True), hist)
    assert not met
    assert "run 800: no scorecard" in why


def test_a_rerun_is_a_retry_and_does_not_count(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: _card(True, attempt=2), 700: _card(True)})
    met, why = st.judge_stable("MC-13", _current(True), hist)
    assert not met
    assert "re-run" in why


def test_one_failing_night_resets_the_streak(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: _card(False), 700: _card(True)})
    met, why = st.judge_stable("MC-13", _current(True), hist)
    assert not met
    assert "run 800: suite did not pass" in why


def test_the_current_run_failing_is_not_met(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: _card(True), 700: _card(True)})
    assert st.judge_stable("MC-13", _current(False), hist)[0] is False


def test_a_manual_run_is_judged_on_scheduled_history_only(tmp_path: Path) -> None:
    two = _history(tmp_path, {800: _card(True), 700: _card(True)})
    met, why = st.judge_stable("MC-13", _current(True, event="workflow_dispatch"), two)
    assert not met and why.startswith("not measured: 2 of 3")
    three = two + [{"run_id": 600, "card": _card(True)}]
    assert st.judge_stable("MC-13", _current(False, event="workflow_dispatch"), three) == (True, "")


def test_a_manual_run_in_history_is_not_counted(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: _card(True, event="workflow_dispatch"), 700: _card(True)})
    met, why = st.judge_stable("MC-13", _current(True), hist)
    assert not met and "not a scheduled run" in why


def test_another_surface_passing_does_not_count(tmp_path: Path) -> None:
    hist = _history(tmp_path, {800: _card(True, surface="MC-04"), 700: _card(True)})
    assert st.judge_stable("MC-13", _current(True), hist)[0] is False


def test_suite_passed_needs_every_live_receipt(tmp_path: Path) -> None:
    ok = {"checks": [{"check": "1-x", "result": "PASS"}]}
    assert sc.suite_passed("MC-13", {"desktop": ok, "phone": ok, "l2": ok})
    assert not sc.suite_passed("MC-13", {"desktop": ok, "phone": ok})
    assert not sc.suite_passed("MC-13", {"desktop": ok, "phone": ok,
                                         "l2": {"checks": [{"check": "8-a", "result": "FAIL"}]}})
    assert sc.suite_passed("MC-00", {"desktop": ok})


def test_scorecard_cli_records_run_and_reads_history(tmp_path: Path) -> None:
    receipts, hist, out = tmp_path / "r", tmp_path / "h", tmp_path / "card.json"
    receipts.mkdir()
    hist.mkdir()
    for rid in (800, 700):
        (hist / str(rid)).mkdir()
        card = {"run": {"event": "schedule", "run_attempt": 1},
                "surfaces": [{"surface": "MC-13", "suite_passed": True}]}
        (hist / str(rid) / "scorecard.json").write_text(json.dumps(card), encoding="utf-8")
    assert sc.main([str(receipts), "--json", str(out), "--event", "schedule",
                    "--run-id", "900", "--run-attempt", "1", "--history", str(hist)]) == 0
    card = json.loads(out.read_text(encoding="utf-8"))
    assert card["run"] == {"event": "schedule", "run_id": 900, "run_attempt": 1}
    row = next(r for r in card["surfaces"] if r["surface"] == "MC-13")
    # No receipts this run, so the suite did not pass and the streak is broken.
    assert row["suite_passed"] is False
    assert row["checks"]["10"]["met"] is False


def test_live_suite_allows_no_retries() -> None:
    # Check 10 says "zero retries used" and judges a run on attempt 1 as
    # retry-free. That holds only while the live config forbids retries.
    config = (ROOT / "dashboard" / "playwright.live.config.ts").read_text(encoding="utf-8")
    assert re.search(r"^\s*retries:\s*0,\s*$", config, re.M), "check 10 assumes retries: 0"
