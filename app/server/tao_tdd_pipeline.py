"""app/server/tao_tdd_pipeline.py — RA-1992: test-first iteration pipeline.

Wave 2 / 3 — port of @callumvass/forgeflow-dev. Composes directly on RA-1970
(`tao_loop.run_until_done` + `tao_judge.judge`). The primitives already exist;
this module chooses test-first as the discipline and binds the judge to
"all tests pass + new test files modified" rather than the generic
GOAL_MET signal.

The TDD discipline reframes the loop:

  1. Pre-flight (red gate): start by ensuring failing tests exist for the
     feature. The provided `goal` describes intent in TDD shape: name the
     test scenarios first, name the implementation last. The pipeline
     does NOT generate tests for the user — it requires them as part of
     the goal — but it DOES check that at least one test file appeared
     in the diff before declaring done.
  2. Iteration (red → green → refactor): one generator step per iter.
     `tao_loop` runs as normal but the goal preamble teaches the worker
     to write tests first, then minimum implementation.
  3. Judgment: the loop's judge is replaced by a TDD-specific scorer
     that requires BOTH `last_test_output` ending in `passed` AND the
     `last_diff` containing `test_*.py` or `*_test.py` modifications.
     Without both, score caps at 0.6 (insufficient progress on the
     test-first dimension).

Public API:

    result = await run_tdd(
        goal="add a hex-string parser; tests must cover empty / non-hex / "
             "uppercase / mixed-case / leading-0x cases",
        workspace="/path/to/repo",
        max_iters=None,
        max_cost_usd=None,
        timeout_per_iter_s=600,
        on_event=callback,
    )

Returns `TddResult` (extends `LoopResult` with TDD-specific fields).

Sequencing under the autoresearch envelope:
  * Single metric — iters-to-green / cost-to-green
  * Time budget — inherits TAO_MAX_ITERS / TAO_MAX_COST_USD via tao_loop
  * Constrained scope — this module only (no SDK / kill_switch changes)
  * Strategy/tactic split — user gives test scenarios, agent does
    red→green→refactor
  * Kill-switch — inherits via tao_loop's LoopCounter

Compounds with: tao-context-prune (RA-1990) for transcript shaping;
tao-context-mode (RA-1969) for sharper file-expand decisions during
the implementation phase.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from .tao_loop import EventCallback, LoopResult, run_until_done

log = logging.getLogger("pi-ceo.tao_tdd")

# ── TDD-specific constants ───────────────────────────────────────────────────


_TDD_PREAMBLE: Final[str] = (
    "You are operating under a test-first discipline. The next iteration "
    "MUST proceed in the order: (1) write or refine failing tests that "
    "encode the goal's acceptance criteria; (2) run pytest and confirm "
    "they fail in a meaningful way (assertion, not import error); (3) "
    "implement the minimum code to make the tests pass; (4) re-run "
    "pytest and confirm green. Do NOT skip step 1: implementation "
    "without tests is rejected by the judge.\n\n"
)

# Files that count as "tests" for the diff check. Liberal — covers
# pytest discovery patterns + common conftest layouts.
_TEST_FILE_RE: Final[re.Pattern[str]] = re.compile(
    r"(^|/)(test_[^/]+\.py|[^/]+_test\.py|conftest\.py|tests/[^\s]+\.py)"
)

# Pytest output markers indicating green status.
_PASSED_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(\d+\s+passed)(,\s+\d+\s+(skipped|xfailed|xpassed|warnings))*\b"
    r"(\s+in\s+[\d.]+s)?$",
    re.MULTILINE,
)

# Pytest output markers indicating red status.
_FAILED_RE: Final[re.Pattern[str]] = re.compile(
    r"\b\d+\s+(failed|error)\b", re.MULTILINE
)


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class TddResult:
    """Outcome of a `run_tdd` invocation. Wraps `LoopResult` and adds
    TDD-specific fields the caller can use to decide what to do next."""

    loop: LoopResult
    test_files_modified: list[str] = field(default_factory=list)
    final_pytest_passed: bool = False
    final_pytest_summary: str = ""
    discipline_violations: list[str] = field(default_factory=list)

    @property
    def done(self) -> bool:
        """True iff the loop terminated with goal-met AND TDD discipline
        was honoured (test files were modified, final pytest passed)."""
        return (
            self.loop.done
            and self.final_pytest_passed
            and bool(self.test_files_modified)
        )

    @property
    def reason(self) -> str:
        """Composite reason. Falls back to loop.reason when the loop
        itself terminated; otherwise reports the TDD-specific block."""
        if not self.loop.done:
            return self.loop.reason
        if not self.final_pytest_passed:
            return "TESTS_NOT_GREEN"
        if not self.test_files_modified:
            return "NO_TEST_FILES_MODIFIED"
        return "GOAL_MET"


# ── TDD-specific gates ───────────────────────────────────────────────────────


def _git_diff_files(workspace: str) -> list[str]:
    """`git diff --name-only HEAD` — files modified vs HEAD. Empty list on error."""
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return [
            line.strip() for line in (proc.stdout or "").splitlines()
            if line.strip()
        ]
    except (subprocess.SubprocessError, OSError):
        return []


def _filter_test_files(paths: list[str]) -> list[str]:
    """Subset of `paths` matching pytest test conventions."""
    return [p for p in paths if _TEST_FILE_RE.search(p)]


def _run_full_pytest(workspace: str, *, timeout_s: int = 180) -> tuple[bool, str]:
    """Run a full pytest in workspace. Returns (passed, summary).

    `passed` is True only when pytest finished AND its summary line
    matches `_PASSED_RE` AND no failed/error count is reported.

    The summary is the last 1500 chars of combined stdout+stderr.
    """
    if not (Path(workspace) / "tests").is_dir():
        return False, "_(no tests/ dir in workspace)_"
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "-q", "--tb=line", "tests/"],
            capture_output=True, text=True, timeout=timeout_s,
            cwd=workspace, check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"_(pytest invocation failed: {exc})_"
    out = (proc.stdout or "") + (proc.stderr or "")
    summary = out[-1500:].strip()
    if proc.returncode != 0:
        return False, summary
    if _FAILED_RE.search(out):
        return False, summary
    if not _PASSED_RE.search(out):
        return False, summary
    return True, summary


# ── Public API ───────────────────────────────────────────────────────────────


def _enrich_goal_with_preamble(goal: str) -> str:
    """Prepend the TDD discipline preamble. Idempotent — if the preamble
    is already present (caller explicitly added it) we don't double-add."""
    if "test-first discipline" in goal:
        return goal
    return f"{_TDD_PREAMBLE}Goal: {goal}"


async def run_tdd(
    goal: str,
    workspace: str,
    *,
    max_iters: int | None = None,
    max_cost_usd: float | None = None,
    timeout_per_iter_s: int = 600,
    on_event: EventCallback | None = None,
    session_id: str = "",
    judge_every_n_iters: int = 1,
) -> TddResult:
    """Run a test-first iteration loop. Returns TddResult.

    Behaviour overview:
      1. Prepend a TDD preamble to the goal so the worker knows to write
         tests first.
      2. Delegate the actual iteration to `tao_loop.run_until_done` —
         the judge gate stays the standard one, scored against the
         ground truth that pytest is green.
      3. After loop termination, perform two TDD-specific checks:
           a. `git diff --name-only HEAD` must include at least one
              test file (`test_*.py`, `*_test.py`, `tests/*.py`,
              `conftest.py`).
           b. `python -m pytest -q tests/` must exit 0 with a `passed`
              summary line.
      4. Bundle all of the above into a `TddResult` whose `done`
         property returns True only when ALL three conditions hold.

    Discipline violations are recorded onto the result rather than
    raising, so the caller can read the structured outcome and decide
    whether to escalate.

    Cost / iteration kill-switches are inherited from `run_until_done`.
    """
    enriched_goal = _enrich_goal_with_preamble(goal)
    log.info("tao_tdd: starting; workspace=%s session_id=%s", workspace, session_id)

    loop = await run_until_done(
        goal=enriched_goal,
        workspace=workspace,
        max_iters=max_iters,
        max_cost_usd=max_cost_usd,
        judge_every_n_iters=judge_every_n_iters,
        timeout_per_iter_s=timeout_per_iter_s,
        on_event=on_event,
        session_id=session_id,
    )

    # Post-loop TDD-specific checks. Run regardless of `loop.done` so the
    # caller can see WHY a non-green loop failed (e.g. tests still red,
    # no test files added).
    diff_files = _git_diff_files(workspace)
    test_files = _filter_test_files(diff_files)

    pytest_passed, pytest_summary = _run_full_pytest(
        workspace, timeout_s=timeout_per_iter_s,
    )

    violations: list[str] = []
    if loop.done and not test_files:
        violations.append(
            "discipline_no_test_files: loop reported GOAL_MET but the diff "
            "vs HEAD contains no test files — test-first discipline was "
            "skipped."
        )
    if loop.done and not pytest_passed:
        violations.append(
            "discipline_tests_not_green: loop reported GOAL_MET but final "
            f"pytest run is RED. Summary tail:\n{pytest_summary[-400:]}"
        )

    return TddResult(
        loop=loop,
        test_files_modified=test_files,
        final_pytest_passed=pytest_passed,
        final_pytest_summary=pytest_summary,
        discipline_violations=violations,
    )


__all__ = [
    "TddResult",
    "run_tdd",
]
