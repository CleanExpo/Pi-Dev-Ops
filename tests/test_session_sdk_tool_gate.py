"""Wiring tests for the session_sdk tool-gate adapter.

The pure decision logic is covered in test_tool_gate.py. Here we verify the SDK
adapter shape: can_use_tool returns the right PermissionResult, the streaming
wrapper yields the documented message dict, and escalation is best-effort.
"""
from __future__ import annotations

import asyncio

from app.server import session_sdk


def _run(coro):
    return asyncio.run(coro)


def test_stream_wrapper_yields_one_user_message():
    async def collect():
        return [m async for m in session_sdk._tool_gate_stream("hello", "sid-1")]

    msgs = _run(collect())
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "user"
    assert m["message"] == {"role": "user", "content": "hello"}
    assert m["parent_tool_use_id"] is None
    assert m["session_id"] == "sid-1"


def test_stream_wrapper_defaults_session_id():
    async def first():
        async for m in session_sdk._tool_gate_stream("x", ""):
            return m

    assert _run(first())["session_id"] == "tao"


def test_can_use_tool_allows_benign():
    cb = session_sdk._make_can_use_tool()
    res = _run(cb("Bash", {"command": "ls -la"}, None))
    assert res.behavior == "allow"
    assert res.updated_input == {"command": "ls -la"}


def test_can_use_tool_denies_irreversible_and_escalates(monkeypatch):
    sent = {}

    # Intercept the lazy escalation import path.
    import swarm.telegram_alerts as ta

    def fake_send(message, severity="info", bot_name="Swarm", dedup_key=None):
        sent.update(message=message, severity=severity, dedup_key=dedup_key)
        return True

    monkeypatch.setattr(ta, "send", fake_send)

    cb = session_sdk._make_can_use_tool()
    res = _run(cb("Bash", {"command": "rm -rf /tmp/x"}, None))
    assert res.behavior == "deny"
    assert "irreversible" in res.message.lower()
    assert res.interrupt is False
    assert sent["severity"] == "critical"
    assert sent["dedup_key"] == "toolgate:rm-rf"


def test_escalation_failure_is_swallowed(monkeypatch):
    import swarm.telegram_alerts as ta

    def boom(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(ta, "send", boom)

    cb = session_sdk._make_can_use_tool()
    # Must still return a clean deny despite escalation raising.
    res = _run(cb("Bash", {"command": "git push --force origin main"}, None))
    assert res.behavior == "deny"


def test_gate_default_off():
    from app.server import config
    # Safety default: the proven bypassPermissions path stays active unless
    # explicitly enabled.
    assert config.TAO_TOOL_GATE is False
