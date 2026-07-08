"""Prove-It Gate — golden suite 2: Terminal Orchestrator write tier (RA-7012).

Second agent under the gate (ADR-006 closure, NEXT ACTION 3). Deterministic,
code-checkable assertions over `swarm.tmux_writer` — no LLM judge, no provider
keys, no real tmux (a fake libtmux server stands in, matching the unit-test
convention in tests/test_tmux_writer.py).

What this suite pins that the unit tests do not: the input→expected CONTRACTS
in data form (evals/golden/tmux_writer.yaml), covering the safety-critical
edges — injection-shaped send payloads, unsafe session names, and above all
the Cap 3 invariant that `close` is L3 human-gated and never autonomous. The
meta-test below makes the dataset itself un-gameable on that invariant: no
future golden case may bless an unapproved kill.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from swarm import tmux_writer

_GOLDEN = Path(__file__).parent / "golden" / "tmux_writer.yaml"
_CASES = yaml.safe_load(_GOLDEN.read_text())["cases"]


# ── Fake libtmux surface (no real tmux in CI) ────────────────────────────────
class _GoldenPane:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    def send_keys(self, text: str, enter: bool = True) -> None:
        self.sent.append((text, enter))


class _GoldenSession:
    def __init__(self, name: str) -> None:
        self.name = name
        self.active_pane = _GoldenPane()
        self.killed = False

    def kill(self) -> None:
        self.killed = True


class _GoldenServer:
    def __init__(self, names: list[str]) -> None:
        self.sessions = [_GoldenSession(n) for n in names]

    def new_session(self, session_name: str, attach: bool = False) -> _GoldenSession:
        self.sessions.append(_GoldenSession(session_name))
        return self.sessions[-1]


def _dispatch(case: dict[str, Any], srv: _GoldenServer, audit_dir: Path) -> dict:
    """Route a golden case to the writer verb it exercises."""
    verb = case["verb"]
    if verb == "send":
        return tmux_writer.send(
            case["session"], case["text"], server=srv, audit_dir=audit_dir
        )
    if verb == "open":
        return tmux_writer.open_session(case["session"], server=srv, audit_dir=audit_dir)
    if verb == "close":
        kwargs: dict[str, Any] = {"server": srv, "audit_dir": audit_dir}
        if case.get("approved"):
            kwargs["approved"] = True
        if case.get("with_draft"):
            kwargs["post_draft"] = lambda **_kw: None
        return tmux_writer.close_session(case["session"], **kwargs)
    raise ValueError(f"unknown golden verb: {verb!r}")


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["id"])
def test_tmux_writer_matches_golden(case: dict[str, Any], tmp_path: Path) -> None:
    srv = _GoldenServer(case.get("sessions", []))
    sessions_before = len(srv.sessions)

    result = _dispatch(case, srv, tmp_path)
    expect = case["expect"]

    assert result["ok"] is expect["ok"], (
        f"{case['id']}: ok {result['ok']!r} != expected {expect['ok']!r} "
        f"(reason: {result.get('reason')!r})"
    )
    if "reason_contains" in expect:
        assert expect["reason_contains"] in result.get("reason", ""), (
            f"{case['id']}: reason {result.get('reason')!r} "
            f"missing {expect['reason_contains']!r}"
        )
    if "status" in expect:
        assert result.get("status") == expect["status"], (
            f"{case['id']}: status {result.get('status')!r} != {expect['status']!r}"
        )
    if "level_required" in expect:
        assert result.get("level_required") == expect["level_required"], (
            f"{case['id']}: level_required {result.get('level_required')!r} "
            f"!= {expect['level_required']!r}"
        )

    # Side-effect invariants — a refusal must leave tmux untouched.
    if "keystrokes_sent" in expect:
        keystrokes = [k for s in srv.sessions for k in s.active_pane.sent]
        assert bool(keystrokes) is expect["keystrokes_sent"], (
            f"{case['id']}: keystrokes {keystrokes!r} vs "
            f"expected sent={expect['keystrokes_sent']}"
        )
    if "killed" in expect:
        assert any(s.killed for s in srv.sessions) is expect["killed"], (
            f"{case['id']}: killed-state mismatch (expected {expect['killed']})"
        )
    if "session_created" in expect:
        created = len(srv.sessions) > sessions_before
        assert created is expect["session_created"], (
            f"{case['id']}: session_created {created} != {expect['session_created']}"
        )


def test_dataset_never_blesses_autonomous_close() -> None:
    """Anti-gaming guard on the dataset itself (Cap 3 invariant).

    `close` is L3 human-gated. A future edit that adds a golden case where an
    UNAPPROVED close succeeds or kills would legitimise autonomous kill — this
    meta-test makes such a dataset unmergeable.
    """
    for case in _CASES:
        if case["verb"] == "close" and not case.get("approved"):
            assert case["expect"]["ok"] is False, (
                f"{case['id']}: unapproved close must never expect ok=True"
            )
            assert case["expect"]["killed"] is False, (
                f"{case['id']}: unapproved close must never expect killed=True"
            )
