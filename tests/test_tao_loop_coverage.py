"""UNI-2650: judge GOAL_MET is not completion when coverage fails.

These tests are the DoD probe for `ver-loop-coverage-gated`. A grep for the
import is not evidence; this file is.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.server.coverage_gate import (
    evaluate_workspace,
    resolve_dod_paths,
    workspace_coverage_failed,
)


_FAILING_DOD = (
    "project_id: fixture\n"
    "requirements:\n"
    "  - id: missing-marker\n"
    "    check: path_exists\n"
    "    path: DOES_NOT_EXIST.txt\n"
)
_PASSING_DOD = (
    "project_id: fixture\n"
    "requirements:\n"
    "  - id: marker\n"
    "    check: path_exists\n"
    "    path: marker.txt\n"
)
_GREEN_ENV = dict(
    TAO_MAX_ITERS="100",
    TAO_MAX_COST_USD="100.00",
    TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
)


def _reload(monkeypatch, **env):
    for key, value in {**_GREEN_ENV, **env}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, str(value))
    import app.server.tao_loop as tl
    return tl


def _verdict(reason="GOAL_MET", done=True, score=0.95):
    from app.server.tao_judge import JudgeVerdict
    return JudgeVerdict(
        done=done, reason=reason, score=score, next_action_hint="x",
    )


def _state(iters, _workspace):
    from app.server.tao_judge import JudgeState
    return JudgeState(iters=iters)


def _write_dod(root: Path, body: str, name: str = "fixture.dod.yaml") -> Path:
    dod_dir = root / "config" / "harness" / "dod"
    dod_dir.mkdir(parents=True)
    path = dod_dir / name
    path.write_text(body, encoding="utf-8")
    return path


async def _run(tl, workspace: str, **kwargs):
    sdk = AsyncMock(return_value=(0, "ok", 0.0))
    judge_mock = AsyncMock(return_value=_verdict())
    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", _state):
        return await tl.run_until_done(goal="g", workspace=workspace, **kwargs)


@pytest.mark.asyncio
async def test_judge_done_coverage_fail_is_not_complete(monkeypatch, tmp_path: Path):
    _write_dod(tmp_path, _FAILING_DOD)
    tl = _reload(monkeypatch, TAO_MAX_ITERS="2")

    result = await _run(tl, str(tmp_path), max_iters=2)

    assert result.done is False
    assert result.reason == "COVERAGE_INCOMPLETE"


@pytest.mark.asyncio
async def test_judge_done_coverage_pass_is_complete(monkeypatch, tmp_path: Path):
    (tmp_path / "marker.txt").write_text("ok", encoding="utf-8")
    _write_dod(tmp_path, _PASSING_DOD)
    tl = _reload(monkeypatch)

    result = await _run(tl, str(tmp_path))

    assert result.done is True
    assert result.reason == "GOAL_MET"
    assert result.iters == 1


@pytest.mark.asyncio
async def test_no_dod_does_not_invent_a_coverage_failure(monkeypatch, tmp_path: Path):
    tl = _reload(monkeypatch)

    result = await _run(tl, str(tmp_path))

    assert result.done is True
    assert result.reason == "GOAL_MET"


@pytest.mark.asyncio
async def test_coverage_incomplete_event_is_emitted(monkeypatch, tmp_path: Path):
    _write_dod(tmp_path, _FAILING_DOD)
    tl = _reload(monkeypatch, TAO_MAX_ITERS="2")
    events: list[dict] = []

    result = await _run(tl, str(tmp_path), max_iters=2, on_event=events.append)

    assert result.done is False
    assert any(ev.get("action") == "coverage_incomplete" for ev in events)


def test_resolve_dod_skips_ambiguous_multi_file_trees(tmp_path: Path):
    _write_dod(tmp_path, _FAILING_DOD, "one.dod.yaml")
    (tmp_path / "config" / "harness" / "dod" / "two.dod.yaml").write_text(
        _PASSING_DOD, encoding="utf-8",
    )

    assert resolve_dod_paths(str(tmp_path)) == []
    assert workspace_coverage_failed(str(tmp_path)) is False
    assert evaluate_workspace(str(tmp_path)).skipped is True


def test_explicit_dod_path_blocks_when_probe_fails(tmp_path: Path):
    path = _write_dod(tmp_path, _FAILING_DOD)
    extra = tmp_path / "config" / "harness" / "dod" / "other.dod.yaml"
    extra.write_text(_PASSING_DOD, encoding="utf-8")

    assert workspace_coverage_failed(str(tmp_path), dod_path=str(path)) is True
