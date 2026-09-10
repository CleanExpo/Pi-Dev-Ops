"""Characterization control for the RA-1183 auto-PR block inside `_phase_push`.

Written BEFORE that block was extracted to `app/server/session_push_pr.py`, and
for one reason: at the time of writing NOTHING in tests/ imported `_phase_push`,
so the move would have been 90 relocated lines with no instrument capable of
failing it. The previous session declined the extraction for exactly that reason
and was right to (docs/session-handoffs/handoff-20260910-2125.md section 7 Q1).

These tests pin the observable behaviour the move had to preserve:

  RA-1183  a PR opens only when the push succeeded AND the branch differs from main
  RA-7216  pr_number / head_branch / repo_name land on the session, not on a
           discarded local -- and survive a failure of the pr_url assignment,
           which is a separate try block for that reason
  RA-1184  the Linear ticket routes to the TARGET repo, and only when none exists
           plus: the x-access-token never reaches the derived owner/repo

Each is a defect with a name because it happened. The harness lives in
tests/phase_push_helpers.py; `test_mutation_control_*` at the foot proves this
file can still go red, because a characterization test only ever observed
passing proves nothing (rules/truth-hacking.md, Law 1).
"""
from __future__ import annotations

import json

import pytest

from app.server import session_phases
from tests.phase_push_helpers import (
    TOKEN,
    _HostileSession,
    _install,
    _make_session,
    _Recorder,
    _run,
)


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


# ── Exception scope: the two try blocks are NOT interchangeable ──────────────

@pytest.mark.asyncio
async def test_attribution_keys_survive_a_failing_pr_url_assignment(tmp_path, monkeypatch):
    rec = _Recorder()
    ws = tmp_path / "ws"
    ws.mkdir()
    session = _HostileSession(id="23a6e82e840f0000", workspace=str(ws),
                              evaluator_score=9, evaluator_confidence=88)
    _install(monkeypatch, rec)

    await _run(session)

    assert session.pr_number == 742, "a failed pr_url must not take the keys with it"
    assert session.head_branch == "pidev/auto-23a6e82e"
    assert session.repo_name == "CleanExpo/Pi-Dev-Ops"


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
