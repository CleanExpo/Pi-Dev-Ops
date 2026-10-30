"""Worst-case daily Jev budget for the jev-scout workflow (scripts/jev_scout_budget.py)."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "jev_scout_budget.py"
_SPEC = importlib.util.spec_from_file_location("jev_scout_budget", _PATH)
budget = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(budget)

API = "https://api.example/repos/o/r/actions"
NOW = datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)
ME = (999, 1)


def _jev_step(started: str | None, completed: str | None) -> dict:
    return {"name": budget.JEV_STEP, "started_at": started, "completed_at": completed}


class FakeGitHub:
    """Serves workflow runs (paged by 100) and per-attempt jobs; records every URL asked."""

    def __init__(self, runs: list[dict], jobs: dict[tuple[int, int], list[dict]]):
        self.runs, self.jobs, self.urls = runs, jobs, []

    def __call__(self, url: str) -> dict:
        self.urls.append(url)
        if "/workflows/" in url:
            page = int(url.rsplit("page=", 1)[1])
            visible = self.runs[:budget.SEARCH_LIMIT]  # GitHub's search cap
            return {"total_count": len(self.runs),
                    "workflow_runs": visible[(page - 1) * 100:page * 100]}
        run_id, attempt = url.split("/runs/", 1)[1].split("/jobs", 1)[0].split("/attempts/")
        steps = self.jobs.get((int(run_id), int(attempt)), [])
        return {"jobs": [{"steps": steps}]}


def _run(run_id: int, cap: str = "0.50", attempts: int = 1) -> dict:
    return {"id": run_id, "run_attempt": attempts, "display_title": f"Jev scout cap={cap}"}


def _spent(fake: FakeGitHub) -> float:
    return budget.spent_today(fake, API, NOW, ME)


def test_first_run_of_the_day_spends_nothing_before_it():
    assert _spent(FakeGitHub([], {})) == 0.0
    assert budget.decide("0.50", 0.0) == (0.50, "")


def test_each_earlier_jev_step_today_is_charged_its_full_cap():
    runs = [_run(1, "0.50"), _run(2, "2.00")]
    jobs = {(1, 1): [_jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:05:00Z")],
            (2, 1): [_jev_step("2026-10-31T02:00:00Z", "2026-10-31T02:05:00Z")]}
    assert _spent(FakeGitHub(runs, jobs)) == 2.50


def test_a_step_that_ran_across_midnight_counts_against_today():
    jobs = {(1, 1): [_jev_step("2026-10-30T23:58:00Z", "2026-10-31T00:03:00Z")]}
    assert _spent(FakeGitHub([_run(1, "1.00")], jobs)) == 1.00


def test_a_step_finished_before_midnight_belongs_to_yesterday():
    jobs = {(1, 1): [_jev_step("2026-10-30T22:00:00Z", "2026-10-30T22:05:00Z")]}
    assert _spent(FakeGitHub([_run(1, "1.00")], jobs)) == 0.0


def test_a_step_still_running_counts():
    jobs = {(1, 1): [_jev_step("2026-10-31T08:59:00Z", None)]}
    assert _spent(FakeGitHub([_run(1, "1.00")], jobs)) == 1.00


def test_a_refused_run_whose_jev_step_never_started_costs_nothing():
    jobs = {(1, 1): [_jev_step(None, None)]}
    assert _spent(FakeGitHub([_run(1, "2.00")], jobs)) == 0.0


def test_a_skipped_jev_step_costs_nothing_even_with_timestamps():
    step = _jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:00:00Z") | {"conclusion": "skipped"}
    assert _spent(FakeGitHub([_run(1, "2.00")], {(1, 1): [step]})) == 0.0


def test_a_cancelled_jev_step_is_still_charged():
    step = _jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:02:00Z") | {"conclusion": "cancelled"}
    assert _spent(FakeGitHub([_run(1, "2.00")], {(1, 1): [step]})) == 2.00


def test_every_attempt_of_a_rerun_is_charged():
    jobs = {(1, 1): [_jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:01:00Z")],
            (1, 2): [_jev_step("2026-10-31T02:00:00Z", "2026-10-31T02:01:00Z")]}
    assert _spent(FakeGitHub([_run(1, "1.00", attempts=2)], jobs)) == 2.00


def test_this_attempt_is_not_charged_but_its_earlier_attempts_are():
    me_run = {"id": 999, "run_attempt": 2, "display_title": "Jev scout cap=1.00"}
    jobs = {(999, 1): [_jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:01:00Z")],
            (999, 2): [_jev_step("2026-10-31T08:59:00Z", None)]}
    assert budget.spent_today(FakeGitHub([me_run], jobs), API, NOW, (999, 2)) == 1.00


def test_every_page_of_run_history_is_read():
    runs = [_run(i, "0.10") for i in range(1, 251)]
    jobs = {(i, 1): [_jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:01:00Z")]
            for i in range(1, 251)}
    fake = FakeGitHub(runs, jobs)
    assert _spent(fake) == 25.00
    assert sum("/workflows/" in u for u in fake.urls) == 3


def test_history_query_starts_the_day_before_so_midnight_runs_are_seen():
    fake = FakeGitHub([], {})
    _spent(fake)
    assert "created=%3E%3D2026-10-30" in fake.urls[0]


@pytest.mark.parametrize("title", [None, "", "Jev scout", "Jev scout cap=abc", "Jev scout cap=9",
                                   "Jev scout cap=0.01 cap=2", "cap=0.01 Jev scout cap=2"])
def test_an_unknown_or_oversized_cap_is_charged_at_the_maximum(title):
    assert budget.run_cap(title) == budget.RUN_CAP_MAX


@pytest.mark.parametrize("raw", ["0.50", "0.01 cap=2", "1e-9", "nan", "-1", "7", " 0.3 ", "inf"])
def test_a_run_is_charged_at_least_what_it_was_allowed_to_spend(raw):
    """The charge read back from the title is never below the cap the run itself applied."""
    assert budget.run_cap(budget._TITLE_PREFIX + raw) >= budget.clamp_cap(raw)


@pytest.mark.parametrize("raw, expected", [
    ("0.50", 0.50), ("0", 0.01), ("-3", 0.01), ("5", 2.00), ("nan", 2.00), ("", 2.00), (None, 2.00)])
def test_requested_cap_is_clamped(raw, expected):
    assert budget.clamp_cap(raw) == expected


def test_run_gets_only_what_is_left_of_twenty():
    assert budget.decide("2.00", 19.25) == (0.75, "")


@pytest.mark.parametrize("raw", ["0.01 cap=2", "1e-9", "nan", "-1", " 0.3", "0.5" + " " * 300,
                                 "", None, "0.123", "100"])
def test_a_cap_that_is_not_a_plain_short_number_is_refused(raw):
    cap, refuse = budget.decide(raw, 0.0)
    assert cap == 0.0 and "plain number" in refuse


def test_run_refuses_when_nothing_is_left():
    cap, refuse = budget.decide("0.50", 20.00)
    assert cap == 0.0 and "daily Jev budget used" in refuse


def test_missing_runs_key_fails_closed():
    with pytest.raises(RuntimeError):
        _spent(lambda url: {"message": "Bad credentials"})


def test_history_at_the_search_limit_fails_closed():
    """1,000 newer cancelled runs must not hide older ones that spent."""
    runs = [_run(i, "2.00") for i in range(1, 1011)]
    jobs = {(i, 1): [_jev_step("2026-10-31T01:00:00Z", "2026-10-31T01:01:00Z")]
            for i in range(1001, 1011)}
    with pytest.raises(RuntimeError, match="search limit"):
        _spent(FakeGitHub(runs, jobs))


def test_a_short_read_against_total_count_fails_closed():
    def fetch(url: str) -> dict:
        if "/workflows/" in url:
            return {"total_count": 5, "workflow_runs": [_run(1)]}
        return {"jobs": []}
    with pytest.raises(RuntimeError, match="read 1 of 5"):
        _spent(fetch)


def test_missing_total_count_fails_closed():
    with pytest.raises(RuntimeError):
        _spent(lambda url: {"workflow_runs": []})


def test_missing_jobs_key_fails_closed():
    def fetch(url: str) -> dict:
        return ({"total_count": 1, "workflow_runs": [_run(1)]} if "/workflows/" in url
                else {"message": "nope"})
    with pytest.raises(RuntimeError):
        _spent(fetch)
