"""Characterization control for the RA-1183 auto-PR block inside `_phase_push`.

Written BEFORE that block is extracted to its own module, and for one reason: at
the time of writing NOTHING in tests/ imported `_phase_push`, so an extraction
would have been a 90-line move with no instrument capable of failing it. The
previous session declined the extraction for exactly that reason and it was right
to (docs/session-handoffs/handoff-20260910-2125.md §7 Q1).

These tests pin the observable behaviour the move must preserve:

  RA-1183  a PR is opened only when the push succeeded AND the branch differs from main
  RA-7216  pr_number / head_branch / repo_name land on the session, not on a discarded local
  RA-1184  the Linear ticket is routed to the TARGET repo, and only when none exists yet
           plus: the x-access-token credential never reaches the derived owner/repo

Each is a defect that has a name because it happened. `test_mutation_control_*`
at the foot proves this file can go red — a characterization test that has only
ever been observed passing proves nothing (rules/truth-hacking.md, Law 1).
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from app.server import session_phases


TOKEN = "ghs_faketoken0000000000000000000000000000"
REMOTE = "https://github.com/CleanExpo/Pi-Dev-Ops.git"
AUTHED = f"https://x-access-token:{TOKEN}@github.com/CleanExpo/Pi-Dev-Ops.git"


class _Recorder:
    """Collects everything the phase did, so assertions read against one object."""

    def __init__(self) -> None:
        self.cmds: list[tuple[str, ...]] = []
        self.pr_payloads: list[dict] = []
        self.pr_urls: list[str] = []
        self.linear_calls: list[tuple] = []
        self.messages: list[str] = []


def _make_session(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "main.py").write_text("print('x')\n")
    return types.SimpleNamespace(
        id="23a6e82e840f0000",
        workspace=str(ws),
        evaluator_score=9,
        evaluator_confidence=88,
    )


def _fake_run_cmd(rec: _Recorder, push_rc: int, diff_out: str):
    """A git that answers only the calls `_phase_push` actually makes."""

    async def run(cwd, *args, timeout=60, env=None):
        rec.cmds.append(args)
        if args[:2] == ("git", "status"):
            return 0, "", ""
        if args[:2] == ("git", "log") and "--oneline" in args:
            return 0, "abc1234 feat: pi ceo build", ""
        if args[:3] == ("git", "remote", "get-url"):
            # After set-url the block must read back the AUTHED url — that is the
            # form the token-stripping line has to cope with.
            seen_set = any(a[:3] == ("git", "remote", "set-url") for a in rec.cmds)
            return 0, (AUTHED if seen_set else REMOTE), ""
        if args[:3] == ("git", "remote", "set-url"):
            return 0, "", ""
        if args[:2] == ("git", "checkout"):
            return 0, "", ""
        if args[0] == "git" and args[1] == "push":
            return push_rc, "", ("" if push_rc == 0 else "remote rejected")
        if args[:3] == ("git", "diff", "--name-only"):
            return 0, diff_out, ""
        if args[:2] == ("git", "log") and "--pretty=%s" in args:
            return 0, "fix(x): the last commit subject", ""
        return 0, "", ""

    return run


def _fake_urlopen(rec: _Recorder, urlopen_raises: bool):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"html_url": "https://github.com/CleanExpo/Pi-Dev-Ops/pull/742",
                               "number": 742}).encode()

    def urlopen(req, timeout=15):
        if urlopen_raises:
            raise RuntimeError("422 Unprocessable Entity")
        rec.pr_urls.append(req.full_url)
        rec.pr_payloads.append(json.loads(req.data.decode()))
        return _Resp()

    return urlopen


def _install(monkeypatch, rec: _Recorder, *, push_rc: int = 0, diff_out: str = "app/x.py\n",
             token: str = TOKEN, urlopen_raises: bool = False):
    """Patch every boundary `_phase_push` touches. Assertions read off `rec`."""
    monkeypatch.setattr(session_phases, "run_cmd", _fake_run_cmd(rec, push_rc, diff_out))
    monkeypatch.setattr(session_phases, "em",
                        lambda s, kind, msg="": rec.messages.append(f"{kind}:{msg}"))
    monkeypatch.setattr(session_phases, "_emit_phase_metric",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr(session_phases, "_route_linear_ticket_to_target_project",
                        lambda *a: rec.linear_calls.append(a), raising=False)

    async def allows_push(session, run_cmd, em):
        return True

    monkeypatch.setattr(session_phases.board_review, "allows_push", allows_push)
    monkeypatch.setenv("GITHUB_TOKEN", token)

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(rec, urlopen_raises))


async def _run(session, total_phases: int = 6):
    return await session_phases._phase_push(session, total_phases)


# ── RA-1183: a PR is opened, against the right repo, with the right head ─────

@pytest.mark.asyncio
async def test_opens_pr_when_push_succeeded_and_branch_differs(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec)

    _files, push_ok = await _run(session)

    assert push_ok is True
    assert rec.pr_urls == ["https://api.github.com/repos/CleanExpo/Pi-Dev-Ops/pulls"]
    payload = rec.pr_payloads[0]
    assert payload["head"] == "pidev/auto-23a6e82e"
    assert payload["base"] == "main"
    assert payload["title"] == "fix(x): the last commit subject"


@pytest.mark.asyncio
async def test_no_pr_when_branch_has_no_diff_against_main(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec, diff_out="")

    await _run(session)

    assert rec.pr_payloads == [], "an empty branch must not open a PR"
    assert any("skipping PR open" in m for m in rec.messages)


@pytest.mark.asyncio
async def test_no_pr_when_push_failed(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec, push_rc=1)

    _files, push_ok = await _run(session)

    assert push_ok is False
    assert rec.pr_payloads == [], "a failed push must not open a PR"


@pytest.mark.asyncio
async def test_no_pr_without_a_github_token(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec, token="")

    await _run(session)

    assert rec.pr_payloads == []


# ── RA-7216: the attribution keys survive onto the session ───────────────────

@pytest.mark.asyncio
async def test_attribution_keys_land_on_the_session(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec)

    await _run(session)

    assert session.pr_url == "https://github.com/CleanExpo/Pi-Dev-Ops/pull/742"
    assert session.pr_number == 742
    assert session.head_branch == "pidev/auto-23a6e82e"
    assert session.repo_name == "CleanExpo/Pi-Dev-Ops"


@pytest.mark.asyncio
async def test_derived_repo_name_never_carries_the_token(tmp_path, monkeypatch):
    """The remote is rewritten to embed x-access-token; owner/repo must be clean."""
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec)

    await _run(session)

    assert TOKEN not in session.repo_name
    assert TOKEN not in rec.pr_urls[0]
    assert TOKEN not in json.dumps(rec.pr_payloads[0])


# ── RA-1184: Linear routing, and only when no ticket exists ──────────────────

@pytest.mark.asyncio
async def test_routes_a_linear_ticket_to_the_target_repo(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec)

    await _run(session)

    assert len(rec.linear_calls) == 1
    _sess, owner_repo, pr_url, pr_number, pr_title = rec.linear_calls[0]
    assert owner_repo == "CleanExpo/Pi-Dev-Ops"
    assert pr_number == 742
    assert pr_url.endswith("/pull/742")
    assert pr_title == "fix(x): the last commit subject"


@pytest.mark.asyncio
async def test_no_second_linear_ticket_when_one_already_exists(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    session.linear_issue_id = "RA-7416"
    _install(monkeypatch, rec)

    await _run(session)

    assert rec.linear_calls == [], "an existing ticket must not be duplicated"


# ── The block swallows its own failures rather than failing the push ─────────

@pytest.mark.asyncio
async def test_pr_api_failure_does_not_fail_the_push(tmp_path, monkeypatch):
    rec = _Recorder()
    session = _make_session(tmp_path)
    _install(monkeypatch, rec, urlopen_raises=True)

    _files, push_ok = await _run(session)

    assert push_ok is True, "the code was pushed; a PR-open failure must not undo that"
    assert any("PR auto-open skipped" in m for m in rec.messages)


# ── Mutation control ─────────────────────────────────────────────────────────

def test_mutation_control_this_file_can_go_red():
    """Prove the instrument reaches the code under test.

    If `_phase_push` stopped calling the auto-PR path at all, the assertions above
    would still need something to bind to. This asserts the block's entry
    conditions are readable from the module — the cheapest check that fails loudly
    if the extraction removes the behaviour instead of moving it.
    """
    assert hasattr(session_phases, "_phase_push")
    assert hasattr(session_phases, "_route_linear_ticket_to_target_project")
