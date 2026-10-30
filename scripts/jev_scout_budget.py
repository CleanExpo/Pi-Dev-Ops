"""Daily Jev budget for .github/workflows/jev-scout.yml, by worst-case accounting.

Founder limits (28/10/2026): a hard cap on every Jev run and $20 per UTC day. Two review rounds
broke every design that rebuilt the day's spend from a ledger carried between runs (midnight
rollover, re-runs, a lost cache, a run history longer than one page), so this keeps no ledger.
Every Jev step that could have spent today is charged its FULL per-run cap, and this run may
spend only what is left of $20. Over-counting is the price; under-counting is impossible
unless the GitHub API itself lies.

A Jev step counts against today when it finished (or is still running) at or after 00:00 UTC
today, whatever day its run was created. Every page and every attempt is read; any API error
raises, so the step fails closed.

Prints `usd=<cap for this run>` and `refuse=<reason or empty>` lines for $GITHUB_OUTPUT.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable

DAILY_CAP_USD = 20.00
RUN_CAP_MIN, RUN_CAP_MAX = 0.01, 2.00
JEV_STEP = "Run Jev scout"
WORKFLOW = "jev-scout.yml"
SEARCH_LIMIT = 1000  # GitHub: a filtered List workflow runs search returns at most 1,000
_TITLE_PREFIX = "Jev scout cap="  # must match run-name in jev-scout.yml
_PLAIN_CAP = re.compile(r"[0-9]{1,2}(?:\.[0-9]{1,2})?")

Fetch = Callable[[str], dict]


def clamp_cap(raw: str | None) -> float:
    """The per-run cap the workflow applies to a typed value; unparseable input is the maximum."""
    try:
        value = float(raw or "")
    except ValueError:
        return RUN_CAP_MAX
    if value != value:  # NaN
        return RUN_CAP_MAX
    return max(RUN_CAP_MIN, min(value, RUN_CAP_MAX))


def run_cap(display_title: str | None) -> float:
    """A past run's cap, read back from its run-name; unknown means the maximum.

    The title is `Jev scout cap=<raw input>`, so the WHOLE raw input goes through the same
    clamp the run applied. Searching for a number inside it would let an input such as
    `0.01 cap=2` be charged 0.01 while the run, failing to parse it, used 2.00.
    """
    title = display_title or ""
    if not title.startswith(_TITLE_PREFIX):
        return RUN_CAP_MAX
    return clamp_cap(title[len(_TITLE_PREFIX):])


def _parse_time(stamp: str | None) -> datetime | None:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None


def _all_runs(fetch: Fetch, api: str, since_day: str) -> list[dict]:
    """Every run created since since_day, or an error. A created-filtered search returns at
    most SEARCH_LIMIT runs however many match, so a history at that size is refused rather than
    counted from a window that may have dropped the runs that spent."""
    runs, page, total = [], 1, None
    while True:
        body = fetch(f"{api}/workflows/{WORKFLOW}/runs?created=%3E%3D{since_day}&per_page=100&page={page}")
        batch, count = body.get("workflow_runs"), body.get("total_count")
        if batch is None or not isinstance(count, int):
            raise RuntimeError("workflow runs response has no workflow_runs or total_count")
        total = count if total is None else max(total, count)
        if total >= SEARCH_LIMIT:
            raise RuntimeError(f"{total} runs since {since_day}: over the search limit, cannot count")
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    if len(runs) < total:
        raise RuntimeError(f"read {len(runs)} of {total} runs since {since_day}")
    return runs


def _jev_step_counts(step: dict, midnight: datetime) -> bool:
    # A skipped step never ran; GitHub may still stamp it with start and finish times.
    if step.get("name") != JEV_STEP or not step.get("started_at") or step.get("conclusion") == "skipped":
        return False
    finished = _parse_time(step.get("completed_at"))
    return finished is None or finished >= midnight


def spent_today(fetch: Fetch, api: str, now: datetime, me: tuple[int, int]) -> float:
    """Worst-case spend of every OTHER Jev attempt that touched today (UTC)."""
    midnight = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    since_day = (midnight - timedelta(days=1)).date().isoformat()
    total = 0.0
    for run in _all_runs(fetch, api, since_day):
        for attempt in range(1, int(run.get("run_attempt") or 1) + 1):
            if (run["id"], attempt) == me:
                continue
            jobs = fetch(f"{api}/runs/{run['id']}/attempts/{attempt}/jobs?per_page=100").get("jobs")
            if jobs is None:
                raise RuntimeError(f"run {run['id']} attempt {attempt}: no jobs in response")
            steps = [s for job in jobs for s in job.get("steps") or []]
            if any(_jev_step_counts(s, midnight) for s in steps):
                total += run_cap(run.get("display_title"))
    return round(total, 2)


def decide(requested: str | None, spent: float) -> tuple[float, str]:
    """(cap for this run, refusal reason or '')."""
    # Only a plain short number may reach Jev, so the run title (which GitHub may shorten)
    # always reads back as exactly the cap the run used.
    if not _PLAIN_CAP.fullmatch(requested or ""):
        return 0.0, f"max_usd must be a plain number such as 0.50, got {requested!r}"
    left = round(DAILY_CAP_USD - spent, 2)
    cap = min(clamp_cap(requested), left)
    if cap < RUN_CAP_MIN:
        return 0.0, f"daily Jev budget used: ${spent:.2f} of ${DAILY_CAP_USD:.2f} charged today (worst case)"
    return cap, ""


def _github_fetch(token: str) -> Fetch:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def fetch(url: str) -> dict:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as reply:
            return json.load(reply)
    return fetch


def main() -> int:
    env = os.environ
    api = f"https://api.github.com/repos/{env['REPO']}/actions"
    me = (int(env["RUN_ID"]), int(env["RUN_ATTEMPT"]))
    spent = spent_today(_github_fetch(env["GH_TOKEN"]), api, datetime.now(timezone.utc), me)
    cap, refuse = decide(env.get("REQUESTED"), spent)
    print(f"usd={cap:.2f}")
    print(f"spent={spent:.2f}")
    print(f"refuse={refuse}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
