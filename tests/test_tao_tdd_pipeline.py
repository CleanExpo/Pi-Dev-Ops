"""tests/test_tao_tdd_pipeline.py — RA-1992 regression coverage.

Mocks `tao_loop.run_until_done` + the post-loop pytest invocation +
`git diff` so every test runs in milliseconds. The TDD-specific gates
(test-file presence, pytest green) are exercised independently of the
underlying loop / judge.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.tao_judge import JudgeVerdict  # noqa: E402
from app.server.tao_loop import LoopResult  # noqa: E402
from app.server import tao_tdd_pipeline as tdd  # noqa: E402

# Per-test mark on the async tests below — applying file-wide pytestmark
# would bog down the synchronous helpers with a useless asyncio marker.


def _make_loop_result(*, done: bool, reason: str = "GOAL_MET",
                       iters: int = 3, cost_usd: float = 0.05) -> LoopResult:
    return LoopResult(
        done=done, reason=reason, iters=iters, cost_usd=cost_usd,
        judge_history=[
            JudgeVerdict(done=done, reason=reason, score=1.0 if done else 0.4,
                          next_action_hint=""),
        ],
        final_state=None,
    )


# ── Goal preamble ────────────────────────────────────────────────────────────


def test_preamble_added_to_naive_goal():
    out = tdd._enrich_goal_with_preamble("implement hex parser")
    assert "test-first discipline" in out
    assert "implement hex parser" in out


def test_preamble_idempotent_when_already_present():
    seed = "You are operating under a test-first discipline. Goal: x"
    out = tdd._enrich_goal_with_preamble(seed)
    # Don't double-add
    assert out.count("test-first discipline") == 1


# ── Diff-file filtering ──────────────────────────────────────────────────────


def test_filter_test_files_pytest_conventions():
    paths = [
        "src/foo.py",
        "tests/test_hex.py",
        "lib/parser_test.py",
        "tests/conftest.py",
        "docs/notes.md",
        "tests/integration/test_e2e.py",
    ]
    out = tdd._filter_test_files(paths)
    assert "tests/test_hex.py" in out
    assert "lib/parser_test.py" in out
    assert "tests/conftest.py" in out
    assert "tests/integration/test_e2e.py" in out
    assert "src/foo.py" not in out
    assert "docs/notes.md" not in out


def test_filter_test_files_empty():
    assert tdd._filter_test_files([]) == []


def test_filter_test_files_no_matches():
    assert tdd._filter_test_files(["src/a.py", "main.py"]) == []


# ── Pytest output parsing ────────────────────────────────────────────────────


def test_passed_regex_matches_typical_summary():
    sample = "...                                                       [100%]\n12 passed in 0.42s"
    assert tdd._PASSED_RE.search(sample) is not None
    assert tdd._FAILED_RE.search(sample) is None


def test_failed_regex_matches_typical_summary():
    sample = "============== 1 failed, 11 passed in 0.55s ==============="
    assert tdd._FAILED_RE.search(sample) is not None


def test_passed_regex_no_match_on_empty():
    assert tdd._PASSED_RE.search("") is None


# ── _run_full_pytest ─────────────────────────────────────────────────────────


def test_run_full_pytest_no_tests_dir(tmp_path):
    """Workspace without tests/ → returns False with helpful summary."""
    passed, summary = tdd._run_full_pytest(str(tmp_path))
    assert passed is False
    assert "no tests/ dir" in summary


def test_run_full_pytest_passes_on_synthetic(tmp_path):
    """Real synthetic project with one passing test → returns True."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_trivial():\n    assert 1 + 1 == 2\n"
    )
    passed, summary = tdd._run_full_pytest(str(tmp_path), timeout_s=30)
    assert passed is True
    assert "passed" in summary


def test_run_full_pytest_red_on_synthetic(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_failing():\n    assert False\n"
    )
    passed, summary = tdd._run_full_pytest(str(tmp_path), timeout_s=30)
    assert passed is False
    assert "failed" in summary or "error" in summary


# ── run_tdd integration ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_tdd_done_when_loop_green_tests_green_and_test_files_in_diff(tmp_path):
    """Happy path: all 3 conditions met → result.done=True."""
    with patch.object(tdd, "run_until_done", new=AsyncMock(
            return_value=_make_loop_result(done=True))) as _, \
         patch.object(tdd, "_git_diff_files",
                      return_value=["src/parser.py", "tests/test_parser.py"]), \
         patch.object(tdd, "_run_full_pytest",
                      return_value=(True, "5 passed in 0.42s")):
        result = await tdd.run_tdd(
            goal="implement parser; tests cover edge cases",
            workspace=str(tmp_path),
        )
    assert result.done is True
    assert result.reason == "GOAL_MET"
    assert "tests/test_parser.py" in result.test_files_modified
    assert result.final_pytest_passed is True
    assert result.discipline_violations == []


@pytest.mark.asyncio
async def test_run_tdd_blocks_done_when_loop_green_but_no_test_files(tmp_path):
    """Loop says GOAL_MET but the diff has no test files → done=False."""
    with patch.object(tdd, "run_until_done", new=AsyncMock(
            return_value=_make_loop_result(done=True))), \
         patch.object(tdd, "_git_diff_files",
                      return_value=["src/parser.py"]), \
         patch.object(tdd, "_run_full_pytest",
                      return_value=(True, "0 passed in 0.01s")):
        result = await tdd.run_tdd(
            goal="implement parser",
            workspace=str(tmp_path),
        )
    assert result.done is False
    assert result.reason == "NO_TEST_FILES_MODIFIED"
    assert result.test_files_modified == []
    assert any("discipline_no_test_files" in v
               for v in result.discipline_violations)


@pytest.mark.asyncio
async def test_run_tdd_blocks_done_when_loop_green_but_pytest_red(tmp_path):
    """Loop says GOAL_MET but pytest is red → done=False."""
    with patch.object(tdd, "run_until_done", new=AsyncMock(
            return_value=_make_loop_result(done=True))), \
         patch.object(tdd, "_git_diff_files",
                      return_value=["tests/test_parser.py"]), \
         patch.object(tdd, "_run_full_pytest",
                      return_value=(False, "1 failed, 0 passed")):
        result = await tdd.run_tdd(
            goal="implement parser",
            workspace=str(tmp_path),
        )
    assert result.done is False
    assert result.reason == "TESTS_NOT_GREEN"
    assert result.final_pytest_passed is False
    assert any("discipline_tests_not_green" in v
               for v in result.discipline_violations)


@pytest.mark.asyncio
async def test_run_tdd_kill_switched_loop_propagates_reason(tmp_path):
    """Loop hits MAX_ITERS → result.done=False, result.reason=loop's reason."""
    with patch.object(tdd, "run_until_done", new=AsyncMock(
            return_value=_make_loop_result(done=False, reason="MAX_ITERS"))), \
         patch.object(tdd, "_git_diff_files", return_value=[]), \
         patch.object(tdd, "_run_full_pytest",
                      return_value=(False, "_(no tests)_")):
        result = await tdd.run_tdd(
            goal="implement parser",
            workspace=str(tmp_path),
        )
    assert result.done is False
    assert result.reason == "MAX_ITERS"
    # No discipline violations recorded — loop didn't claim done.
    assert result.discipline_violations == []


@pytest.mark.asyncio
async def test_run_tdd_passes_loop_kwargs_through(tmp_path):
    """Verify max_iters / max_cost_usd / etc. are forwarded to run_until_done."""
    with patch.object(tdd, "run_until_done", new=AsyncMock(
            return_value=_make_loop_result(done=False, reason="MAX_ITERS"))) as mock_loop, \
         patch.object(tdd, "_git_diff_files", return_value=[]), \
         patch.object(tdd, "_run_full_pytest",
                      return_value=(False, "_(no tests)_")):
        await tdd.run_tdd(
            goal="implement parser",
            workspace=str(tmp_path),
            max_iters=7,
            max_cost_usd=2.50,
            timeout_per_iter_s=300,
            judge_every_n_iters=3,
            session_id="my-session",
        )
    # Inspect the call args
    mock_loop.assert_called_once()
    kwargs = mock_loop.call_args.kwargs
    assert kwargs["max_iters"] == 7
    assert kwargs["max_cost_usd"] == 2.50
    assert kwargs["timeout_per_iter_s"] == 300
    assert kwargs["judge_every_n_iters"] == 3
    assert kwargs["session_id"] == "my-session"
    # The goal passed in must be the enriched (preamble-prepended) one
    assert "test-first discipline" in kwargs["goal"]
    assert "implement parser" in kwargs["goal"]


# ── TddResult composite reason ───────────────────────────────────────────────


def test_tdd_result_reason_loop_not_done():
    r = tdd.TddResult(loop=_make_loop_result(done=False, reason="MAX_COST"))
    assert r.reason == "MAX_COST"


def test_tdd_result_reason_tests_not_green():
    r = tdd.TddResult(
        loop=_make_loop_result(done=True),
        test_files_modified=["tests/test_x.py"],
        final_pytest_passed=False,
    )
    assert r.reason == "TESTS_NOT_GREEN"


def test_tdd_result_reason_no_test_files():
    r = tdd.TddResult(
        loop=_make_loop_result(done=True),
        test_files_modified=[],
        final_pytest_passed=True,
    )
    assert r.reason == "NO_TEST_FILES_MODIFIED"


def test_tdd_result_reason_goal_met_full():
    r = tdd.TddResult(
        loop=_make_loop_result(done=True),
        test_files_modified=["tests/test_x.py"],
        final_pytest_passed=True,
    )
    assert r.reason == "GOAL_MET"
    assert r.done is True
