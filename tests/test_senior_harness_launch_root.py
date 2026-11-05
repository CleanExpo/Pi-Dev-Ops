"""A session whose cwd moves after admission keeps its launch-root receipt.

Claude Code and Cloudroom persist a bare `cd` across Bash calls, and a thread can
move to another worktree. The hook then sees a cwd whose Git root has no receipt
(or no Git root at all) and, before this fallback, denied every write tool with
no way back. These tests pin the fallback and its fail-closed edges.
"""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _global_hook,
    _init_repo,
    _start_hook_session,
    _tamper_env,
    handle_hook,
    json,
    pytest,
)

import setup_hooks  # noqa: E402  (importable once the support module sets sys.path)

OBJECTIVE = "Develop the Senior Harness launch-root fallback"


def _admit_in_repo_a(session: str, env: dict[str, str]) -> None:
    admitted = _global_hook(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(REPO_ROOT), "prompt": OBJECTIVE},
        env,
    )
    assert "froze the primary objective" in admitted["additionalContext"]


def _write_tool(session: str, cwd: Path, env: dict[str, str]) -> dict:
    return _global_hook(
        "PreToolUse",
        {
            "session_id": session,
            "cwd": str(cwd),
            "tool_name": "Write",
            "tool_input": {},
        },
        env,
    )


def _launch_record(tmp_path: Path) -> Path:
    records = list((tmp_path / "state" / "launch-root").glob("*.json"))
    assert len(records) == 1, records
    return records[0]


def test_moved_cwd_falls_back_to_the_launch_root_receipt(tmp_path: Path) -> None:
    env = _tamper_env(tmp_path)
    session = "launch-root-moved"
    _admit_in_repo_a(session, env)
    outside = tmp_path / "not-git"
    outside.mkdir()
    repo_b = tmp_path / "repo-b"
    _init_repo(repo_b)

    for cwd in (outside, repo_b):
        decision = _write_tool(session, cwd, env)
        assert decision.get("permissionDecision") != "deny", (cwd, decision)
        assert OBJECTIVE in decision["additionalContext"], cwd


def test_session_without_a_launch_record_still_denies(tmp_path: Path) -> None:
    env = _tamper_env(tmp_path)
    outside = tmp_path / "not-git"
    outside.mkdir()
    repo_b = tmp_path / "repo-b"
    _init_repo(repo_b)

    for cwd in (outside, repo_b):
        decision = _write_tool("never-admitted", cwd, env)
        assert decision["permissionDecision"] == "deny", cwd


def test_forged_launch_record_does_not_admit(tmp_path: Path) -> None:
    env = _tamper_env(tmp_path)
    session = "launch-root-forged"
    _admit_in_repo_a(session, env)
    record_path = _launch_record(tmp_path)
    forged = json.loads(record_path.read_text(encoding="utf-8"))
    repo_b = tmp_path / "repo-b"
    _init_repo(repo_b)
    forged["launch_root"] = str(repo_b.resolve())
    record_path.write_text(json.dumps(forged), encoding="utf-8")
    outside = tmp_path / "not-git"
    outside.mkdir()

    decision = _write_tool(session, outside, env)
    assert decision["permissionDecision"] == "deny"
    assert "launch-root record is invalid" in decision["permissionDecisionReason"]


def test_launch_record_without_launch_state_still_denies(tmp_path: Path) -> None:
    env = _tamper_env(tmp_path)
    session = "launch-root-cleared"
    _admit_in_repo_a(session, env)
    for state in (tmp_path / "state").glob("*/*.json"):
        if state.parent.name not in {"launch-root", "pending-project", "session-locks"}:
            state.unlink()
    outside = tmp_path / "not-git"
    outside.mkdir()

    decision = _write_tool(session, outside, env)
    assert decision["permissionDecision"] == "deny"


def test_session_clear_discards_the_launch_record(tmp_path: Path) -> None:
    env = _tamper_env(tmp_path)
    session = "launch-root-clear"
    _admit_in_repo_a(session, env)
    _launch_record(tmp_path)
    _global_hook(
        "SessionStart",
        {"session_id": session, "cwd": str(REPO_ROOT), "source": "clear"},
        env,
    )
    assert not list((tmp_path / "state" / "launch-root").glob("*.json"))
    outside = tmp_path / "not-git"
    outside.mkdir()

    decision = _write_tool(session, outside, env)
    assert decision["permissionDecision"] == "deny"


def test_clear_outside_git_still_denies_writes_outside_git(tmp_path: Path) -> None:
    """A clear issued outside Git must not leave the launch receipt usable there."""
    env = _tamper_env(tmp_path)
    session = "launch-root-clear-outside"
    _admit_in_repo_a(session, env)
    outside = tmp_path / "not-git"
    outside.mkdir()
    assert _write_tool(session, outside, env).get("permissionDecision") != "deny"
    _global_hook(
        "SessionStart",
        {"session_id": session, "cwd": str(outside), "source": "clear"},
        env,
    )

    decision = _write_tool(session, outside, env)
    assert decision["permissionDecision"] == "deny"


def test_clear_between_fallback_lookup_and_lock_denies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback must be re-checked under the session lock, not trusted from before it."""
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session = "launch-root-race"
    _start_hook_session(tmp_path / "state", monkeypatch, session_id=session)
    real = setup_hooks.launch_root_state
    calls: list[int] = []

    def lookup_then_clear(session_id: str, surface: str):  # noqa: ANN202
        found = real(session_id, surface)
        if not calls:
            calls.append(1)
            setup_hooks.clear_launch_root(session_id)
        return found

    monkeypatch.setattr(setup_hooks, "launch_root_state", lookup_then_clear)
    outside = tmp_path / "not-git"
    outside.mkdir()
    decision = handle_hook(
        {"session_id": session, "cwd": str(outside), "hook_event_name": "PreToolUse",
         "tool_name": "Write", "tool_input": {}},
        surface="claude", event="PreToolUse",
    )
    assert calls, "the injected clear never ran"
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
