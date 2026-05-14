"""Tests for swarm.screen.hermes_dispatch — Phase 5 (plan 2026-05-13).

We do NOT actually invoke Hermes. Every test mocks asyncio.create_subprocess_exec
and asserts on the returned ScreenResult + the audit log line written to a
tmp path (via the TAO_SCREEN_AUDIT_LOG env override the module respects on
import).
"""
from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Any

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def screen_module(tmp_path, monkeypatch):
    """Reload swarm.screen.hermes_dispatch with audit log + screenshot dir
    pointed at a fresh tmp dir per test so audit assertions stay hermetic."""
    audit_path = tmp_path / "screen_audit.jsonl"
    shots_dir = tmp_path / "screenshots"
    shots_dir.mkdir()

    monkeypatch.setenv("TAO_SCREEN_AUDIT_LOG", str(audit_path))
    monkeypatch.setenv("TAO_HERMES_SCREENSHOT_DIR", str(shots_dir))
    monkeypatch.setenv("TAO_HERMES_BIN", "/fake/hermes")
    monkeypatch.delenv("TAO_SCREEN_DISABLED", raising=False)

    import swarm.screen.hermes_dispatch as mod  # noqa: PLC0415
    mod = importlib.reload(mod)
    return mod, audit_path, shots_dir


def _read_audit(audit_path: Path) -> list[dict[str, Any]]:
    if not audit_path.exists():
        return []
    return [
        json.loads(line) for line in audit_path.read_text("utf-8").splitlines()
        if line.strip()
    ]


def _make_fake_proc(*, returncode: int, stdout: bytes, stderr: bytes = b""):
    """Return a fake asyncio.subprocess.Process double for create_subprocess_exec."""

    class _FakeProc:
        def __init__(self) -> None:
            self.returncode = returncode

        async def communicate(self) -> tuple[bytes, bytes]:
            return stdout, stderr

        def kill(self) -> None:  # pragma: no cover — happy path doesn't kill
            pass

        async def wait(self) -> int:  # pragma: no cover
            return returncode

    return _FakeProc()


# ── Tests ───────────────────────────────────────────────────────────────────


def test_kill_switch_short_circuits_without_subprocess(
    screen_module, monkeypatch,
):
    """TAO_SCREEN_DISABLED=1 → returns disabled=True, never spawns subprocess."""
    mod, audit_path, _ = screen_module
    monkeypatch.setenv("TAO_SCREEN_DISABLED", "1")

    spawn_called = {"count": 0}

    async def boom(*args, **kwargs):
        spawn_called["count"] += 1
        raise AssertionError("subprocess must not be spawned when disabled")

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", boom,
    )

    result = asyncio.run(mod.screen_dispatch("open Finder"))

    assert result.disabled is True
    assert result.ok is False
    assert result.session_id is None
    assert result.screenshots == []
    assert result.wall_seconds == 0.0
    assert "kill-switch" in result.final_text.lower()
    assert spawn_called["count"] == 0

    # Audit row written even on disabled.
    rows = _read_audit(audit_path)
    assert len(rows) == 1
    assert rows[0]["type"] == "screen_dispatch_disabled"
    assert rows[0]["intent"] == "open Finder"
    assert rows[0]["disabled"] is True


def test_goal_prefix_prepends_ralph_loop_directive(
    screen_module, monkeypatch,
):
    """When goal=... is passed, the -q argument starts with `/goal <text>\\n\\n`.

    Hermes v0.13.0 Ralph-loop primitive (PR #18262) pins the agent's
    objective across context compression — without it, long Hour-1 portal
    or BotFather flows drift after ~6 turns.
    """
    mod, _, _ = screen_module

    captured_cmd: list[Any] = []

    async def fake_exec(*args, **kwargs):
        captured_cmd.extend(args)
        return _make_fake_proc(returncode=0, stdout=b"ok\nSession: 20260514_150000_x1\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    asyncio.run(mod.screen_dispatch(
        "Click the Approve button in the Stripe Dashboard",
        goal="Send Duncan's deposit Payment Link",
    ))

    cmd_list = list(captured_cmd)
    q_idx = cmd_list.index("-q")
    intent_value = cmd_list[q_idx + 1]
    assert intent_value.startswith("/goal Send Duncan's deposit Payment Link"), (
        f"expected /goal prefix, got: {intent_value!r}"
    )
    assert "Click the Approve button" in intent_value


def test_no_goal_preserves_intent_unchanged(
    screen_module, monkeypatch,
):
    """When goal is omitted, the intent string passes through unchanged."""
    mod, _, _ = screen_module

    captured_cmd: list[Any] = []

    async def fake_exec(*args, **kwargs):
        captured_cmd.extend(args)
        return _make_fake_proc(returncode=0, stdout=b"ok\nSession: 20260514_150100_x2\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    intent_in = "Take a screenshot of the homepage"
    asyncio.run(mod.screen_dispatch(intent_in))

    cmd_list = list(captured_cmd)
    q_idx = cmd_list.index("-q")
    intent_value = cmd_list[q_idx + 1]
    assert intent_value == intent_in
    assert "/goal" not in intent_value


def test_happy_path_parses_session_id_from_stdout(
    screen_module, monkeypatch,
):
    """Mocked subprocess returns stdout with `Session: <id>` → ok=True + parsed."""
    mod, audit_path, _ = screen_module

    fake_stdout = (
        b"Hermes Agent 0.13.0\n"
        b"Working...\n"
        b"Done.\n"
        b"Session:        20260513_104500_abc123ef\n"
    )

    captured_cmd: list[Any] = []

    async def fake_exec(*args, **kwargs):
        captured_cmd.extend(args)
        return _make_fake_proc(returncode=0, stdout=fake_stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = asyncio.run(mod.screen_dispatch(
        "open the empire dashboard and screenshot it",
    ))

    assert result.ok is True
    assert result.disabled is False
    assert result.error is None
    assert result.session_id == "20260513_104500_abc123ef"
    assert "Hermes Agent" in result.final_text
    assert result.wall_seconds >= 0.0

    # Subprocess invoked with the right shape.
    assert captured_cmd[0] == "/fake/hermes"
    assert captured_cmd[1] == "chat"
    assert "-q" in captured_cmd
    assert "--yolo" in captured_cmd
    assert "--max-turns" in captured_cmd
    # default toolsets joined comma-separated
    assert any(
        isinstance(a, str) and "computer_use" in a and "browser" in a
        for a in captured_cmd
    )

    # Audit row exists with the parsed session_id.
    rows = _read_audit(audit_path)
    assert len(rows) == 1
    assert rows[0]["type"] == "screen_dispatch"
    assert rows[0]["ok"] is True
    assert rows[0]["session_id"] == "20260513_104500_abc123ef"


def test_nonzero_exit_populates_error_field(
    screen_module, monkeypatch,
):
    """Subprocess rc != 0 → ok=False, error contains rc + stderr snippet."""
    mod, audit_path, _ = screen_module

    async def fake_exec(*args, **kwargs):
        return _make_fake_proc(
            returncode=2, stdout=b"", stderr=b"permission denied: AX tree",
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = asyncio.run(mod.screen_dispatch("click the save button"))

    assert result.ok is False
    assert result.disabled is False
    assert result.error is not None
    assert "rc=2" in result.error
    assert "permission denied" in result.error
    assert result.session_id is None

    rows = _read_audit(audit_path)
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["rc"] == 2


def test_audit_log_appended_per_call(screen_module, monkeypatch):
    """Successive calls accumulate one JSONL line each in the audit log."""
    mod, audit_path, _ = screen_module

    fake_stdout = b"Done.\nSession:        20260513_111111_deadbeef\n"

    async def fake_exec(*args, **kwargs):
        return _make_fake_proc(returncode=0, stdout=fake_stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    asyncio.run(mod.screen_dispatch("first action"))
    asyncio.run(mod.screen_dispatch("second action"))
    asyncio.run(mod.screen_dispatch("third action"))

    rows = _read_audit(audit_path)
    assert len(rows) == 3
    intents = [r["intent"] for r in rows]
    assert intents == ["first action", "second action", "third action"]
    for r in rows:
        assert r["type"] == "screen_dispatch"
        assert r["ok"] is True
        assert r["session_id"] == "20260513_111111_deadbeef"
        assert "stdout_snippet" in r
        assert "wall_seconds" in r
