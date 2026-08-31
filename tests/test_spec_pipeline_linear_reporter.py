"""Tests for app/server/spec_pipeline/linear_reporter.py.

`autonomy.comment_on_issue` is mocked in every test — nothing here touches the
real Linear API. The contract under test is narrow and absolute: `report()` never
raises into the pipeline, and it stays silent when it has nothing to write with.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.server import autonomy
from app.server.spec_pipeline import linear_reporter


@pytest.fixture
def comments(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        autonomy, "comment_on_issue",
        lambda key, issue_id, body: calls.append((key, issue_id, body)),
    )
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
    monkeypatch.delenv("SPEC_PIPELINE_LINEAR_REPORT", raising=False)
    return calls


def test_report_posts_a_comment(comments: list) -> None:
    linear_reporter.report("ISSUE-1", "spec approved", "Judge 100/100")
    assert len(comments) == 1
    key, issue_id, body = comments[0]
    assert (key, issue_id) == ("lin_test_key", "ISSUE-1")
    assert "Machine spec pipeline — spec approved" in body
    assert "Judge 100/100" in body


@pytest.mark.parametrize("issue_id", [None, "", "   "])
def test_missing_issue_id_is_a_silent_no_op(comments: list, issue_id: Any) -> None:
    linear_reporter.report(issue_id, "blocked", "no board to tell")
    assert comments == []


def test_missing_linear_key_is_a_silent_no_op(
    comments: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    linear_reporter.report("ISSUE-1", "blocked", "reason")
    assert comments == []


def test_empty_linear_key_counts_as_missing(
    comments: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "   ")
    linear_reporter.report("ISSUE-1", "blocked", "reason")
    assert comments == []


@pytest.mark.parametrize("flag", ["0", "false", "off", "no", "FALSE"])
def test_env_flag_disables_reporting(
    comments: list, monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv("SPEC_PIPELINE_LINEAR_REPORT", flag)
    linear_reporter.report("ISSUE-1", "blocked", "reason")
    assert comments == []
    assert linear_reporter.reporting_enabled() is False


def test_reporting_is_on_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEC_PIPELINE_LINEAR_REPORT", raising=False)
    assert linear_reporter.reporting_enabled() is True


@pytest.mark.parametrize("failure", [
    RuntimeError("Linear 500"),
    ConnectionError("dns"),
    KeyError("nope"),
    Exception("anything at all"),
])
def test_report_never_raises_when_linear_fails(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    def _boom(*_a: Any, **_kw: Any) -> None:
        raise failure

    monkeypatch.setattr(autonomy, "comment_on_issue", _boom)
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
    # No pytest.raises: any escape fails the test by propagating out of it.
    linear_reporter.report("ISSUE-1", "blocked", "reason")


def test_report_never_raises_on_junk_arguments(comments: list) -> None:
    linear_reporter.report("ISSUE-1", "stage", None)  # type: ignore[arg-type]
    assert "(no detail)" in comments[0][2]


def test_long_summaries_are_truncated_not_rejected(comments: list) -> None:
    linear_reporter.report("ISSUE-1", "build started", "x" * 9000)
    assert "_(truncated)_" in comments[0][2]
    assert len(comments[0][2]) < 4200


def test_report_returns_none(comments: list) -> None:
    """Fire-and-forget: there is no success value a caller could branch on."""
    assert linear_reporter.report("ISSUE-1", "stage", "detail") is None


def test_pipeline_calls_the_reporter_at_stage_boundaries() -> None:
    """The join is only closed if run_pipeline actually calls it."""
    from pathlib import Path

    import app.server.spec_pipeline as pipeline_pkg

    src = Path(pipeline_pkg.__file__).read_text(encoding="utf-8")
    assert "from . import linear_reporter" in src
    stages = [
        "spec approved", "boardroom vote", "build started", "PR opened",
        "blocked — proposal boundary", "blocked — proposal validation",
        "blocked — judge gate", "blocked — boardroom", "blocked — diff boundary",
        "blocked — review", "dry complete — no build",
    ]
    missing = [s for s in stages if f'"{s}"' not in src]
    assert not missing, f"run_pipeline never reports: {missing}"
