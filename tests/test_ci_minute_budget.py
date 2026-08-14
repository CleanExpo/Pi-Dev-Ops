"""CI-minute budget guard (RA-7222).

GitHub bills Actions **per job, rounded up to the nearest whole minute**
(https://docs.github.com/en/billing/reference/actions-runner-pricing), and this
repo is private, so every minute is billed against the 2,000/month Free
allowance. A one-job workflow that runs for 7 seconds still costs a full minute.

That pricing shape makes two habits quietly expensive, and both had taken hold:

  * an hourly cron on a 1-job workflow costs ~720 min/month — 36% of the whole
    allowance — regardless of how little it does;
  * `push: branches: ["**"]` alongside `pull_request` runs every PR-branch push
    TWICE (observed on PR #645: the same commit billed at 05:28:54 and again at
    05:29:16).

Neither shows up as a failure. Actions simply stops assigning runners when the
allowance is gone, and every job then fails in ~3 seconds with `runner_id: 0` and
no steps — which reads like a broken build, not an exhausted budget. That is what
happened on 14/08/2026: 12 red checks on a PR whose code was fine.

These tests make the cost visible at review time instead.
"""
from __future__ import annotations

import glob
import os
import re

import pytest

WORKFLOWS = sorted(glob.glob(os.path.join(
    os.path.dirname(__file__), "..", ".github", "workflows", "*.yml")))

# Headroom over the current ~754. Blocks a regression to hourly (+720/mo) while
# leaving room to add daily jobs without touching this file.
MONTHLY_RUN_BUDGET = 900

# 8/day = every 3 hours. Blocks hourly (24) and 2-hourly (12) schedules. A
# genuinely time-critical probe should use an external uptime monitor rather
# than a billed runner, or justify itself by raising this deliberately.
MAX_RUNS_PER_DAY_PER_WORKFLOW = 8


def _runs_per_day(cron: str) -> float:
    """Approximate daily fire count for a 5-field cron expression."""
    minute, hour, dom, _mon, dow = (cron.split() + ["*"] * 5)[:5]

    def count(field: str, span: int) -> int:
        if field == "*":
            return span
        if field.startswith("*/"):
            return max(1, span // int(field[2:]))
        total = 0
        for part in field.split(","):
            if "-" in part:
                lo, hi = part.split("-")
                total += int(hi) - int(lo) + 1
            else:
                total += 1
        return total

    per_day = count(minute, 60) * count(hour, 24)
    if dow != "*":
        per_day = per_day * count(dow, 7) / 7
    if dom != "*":
        per_day = per_day * count(dom, 30) / 30
    return per_day


def _crons(path: str) -> list[str]:
    return re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", open(path, encoding="utf-8").read())


def _on_block(text: str) -> str:
    m = re.search(r"^on:.*?(?=^[a-z])", text, re.S | re.M)
    return m.group(0) if m else ""


def _triggers_on_pull_request(text: str) -> bool:
    return bool(re.search(r"^\s+pull_request\b", _on_block(text), re.M))


# ── scheduled spend ──────────────────────────────────────────────────────────

def test_scheduled_runs_stay_within_budget():
    """MUTATION CONTROL: set any cron back to hourly (`17 * * * *`) and this
    fails — that single change adds ~720 runs/month on its own."""
    total = sum(_runs_per_day(c) for f in WORKFLOWS for c in _crons(f)) * 30
    assert total <= MONTHLY_RUN_BUDGET, (
        f"scheduled workflow runs/month = {total:.0f}, over budget "
        f"{MONTHLY_RUN_BUDGET}. Each run bills at least one minute PER JOB "
        f"against a 2,000-minute Free allowance. Lower a cron frequency, or "
        f"raise MONTHLY_RUN_BUDGET deliberately with the reason."
    )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: os.path.basename(p))
def test_no_workflow_polls_more_often_than_every_three_hours(path):
    for cron in _crons(path):
        per_day = _runs_per_day(cron)
        assert per_day <= MAX_RUNS_PER_DAY_PER_WORKFLOW, (
            f"{os.path.basename(path)} fires {per_day:.0f}x/day (`{cron}`), over "
            f"{MAX_RUNS_PER_DAY_PER_WORKFLOW}. At one billed minute per run that "
            f"is ~{per_day * 30:.0f} min/month from this workflow alone."
        )


# ── duplicate runs ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: os.path.basename(p))
def test_no_workflow_double_fires_on_pr_branch_pushes(path):
    """A wildcard `push` next to `pull_request` bills the same commit twice.

    MUTATION CONTROL: restore `push: branches: ["**"]` in fail-open-check.yml
    and this fails for that file.
    """
    text = open(path, encoding="utf-8").read()
    if not _triggers_on_pull_request(text):
        return
    wildcard_push = re.search(
        r"^\s+push:\s*\n\s+branches:\s*\[\s*[\"']\*\*[\"']\s*\]", _on_block(text), re.M)
    assert not wildcard_push, (
        f"{os.path.basename(path)} triggers on `pull_request` AND on pushes to "
        f'every branch (`branches: ["**"]`). A PR-branch push therefore fires it '
        f"twice for one commit, billing both. Scope push to [main]."
    )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: os.path.basename(p))
def test_pr_workflows_cancel_superseded_runs(path):
    """Without cancel-in-progress, three quick pushes bill three full runs.

    Cancelling is scoped to non-main refs on purpose: a commit that has landed
    on main must always be verified in full, never cancelled by a later push.
    """
    text = open(path, encoding="utf-8").read()
    if not _triggers_on_pull_request(text):
        return
    assert re.search(r"^concurrency:", text, re.M), (
        f"{os.path.basename(path)} runs on pull_request but declares no "
        f"`concurrency` group, so superseded runs are billed to completion."
    )
    assert "cancel-in-progress" in text, (
        f"{os.path.basename(path)} declares `concurrency` without "
        f"`cancel-in-progress`, which queues superseded runs instead of "
        f"cancelling them — they still run, and still bill."
    )
