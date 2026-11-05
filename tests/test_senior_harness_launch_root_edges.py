"""Edges of the launch-root fallback raised in review of PR 969.

Each test pins one way the fallback could govern a call that the code before it
denied: a git probe that failed inside a real repository, a record replaced in
the gap before the lock, and a quarantined pending objective.
"""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _global_hook,
    _pending_file,
    _start_hook_session,
    _tamper_env,
    handle_hook,
    json,
    pytest,
)

import setup_hooks  # noqa: E402  (importable once the support module sets sys.path)
from setup_common import GitProbeError  # noqa: E402

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
        {"session_id": session, "cwd": str(cwd), "tool_name": "Write", "tool_input": {}},
        env,
    )


def test_probe_failure_inside_a_repository_does_not_fall_back(tmp_path: Path) -> None:
    """Only a cwd with no repository at all may use the launch root.

    A `.git` that git cannot use (ownership refusal, broken gitdir, timeout) is
    still a repository whose own rules are unknown, so the old deny stands.
    """
    env = _tamper_env(tmp_path)
    session = "launch-root-broken-repo"
    _admit_in_repo_a(session, env)
    outside = tmp_path / "not-git"
    outside.mkdir()
    assert _write_tool(session, outside, env).get("permissionDecision") != "deny"
    broken = tmp_path / "broken-repo"
    broken.mkdir()
    (broken / ".git").write_text(f"gitdir: {tmp_path / 'missing-gitdir'}\n")
    nested = broken / "sub"
    nested.mkdir()

    for cwd in (broken, nested):
        decision = _write_tool(session, cwd, env)
        assert decision["permissionDecision"] == "deny", (cwd, decision)


def test_refused_probe_in_a_real_checkout_stays_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In-process hook path: git refusing a real checkout (ownership, timeout) raises.

    The raise is what the driver turns into the original deny, with or without
    --allow-non-git. Outside any checkout the same probe failure still falls back.
    """
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session = "launch-root-refused-probe"
    _start_hook_session(tmp_path / "state", monkeypatch, session_id=session)

    def refused(cwd: str) -> Path:
        raise GitProbeError([f"git probe failed for {cwd}: dubious ownership"])

    monkeypatch.setattr(setup_hooks, "_git_root", refused)
    outside = tmp_path / "not-git"
    outside.mkdir()

    def write_from(cwd: Path) -> dict:
        return handle_hook(
            {"session_id": session, "cwd": str(cwd), "hook_event_name": "PreToolUse",
             "tool_name": "Write", "tool_input": {}},
            surface="claude", event="PreToolUse",
        )

    allowed = write_from(outside)["hookSpecificOutput"]
    assert allowed.get("permissionDecision") != "deny", allowed
    with pytest.raises(GitProbeError):
        write_from(REPO_ROOT / "tests")


def test_record_replaced_between_lookup_and_lock_denies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clear and re-admission at the same root in the gap is a new record."""
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session = "launch-root-race-replace"
    base, _ = _start_hook_session(tmp_path / "state", monkeypatch, session_id=session)
    real = setup_hooks.launch_root_state
    calls: list[int] = []

    def lookup_then_replace(session_id: str, surface: str):  # noqa: ANN202
        found = real(session_id, surface)
        if not calls:
            calls.append(1)
            for event, extra in (
                ("SessionStart", {"source": "clear"}),
                ("UserPromptSubmit", {"prompt": "A different objective"}),
            ):
                handle_hook(
                    {**base, "hook_event_name": event, **extra},
                    surface="claude", event=event,
                )
        return found

    monkeypatch.setattr(setup_hooks, "launch_root_state", lookup_then_replace)
    outside = tmp_path / "not-git"
    outside.mkdir()
    decision = handle_hook(
        {"session_id": session, "cwd": str(outside), "hook_event_name": "PreToolUse",
         "tool_name": "Write", "tool_input": {}},
        surface="claude", event="PreToolUse",
    )
    assert calls, "the injected replacement never ran"
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_quarantined_pending_objective_denies_the_fallback(tmp_path: Path) -> None:
    """An invalid pending objective keeps the session denied, fallback or not."""
    env = _tamper_env(tmp_path)
    session = "launch-root-quarantine"
    _admit_in_repo_a(session, env)
    outside = tmp_path / "not-git"
    outside.mkdir()
    _global_hook(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(outside), "prompt": "Second objective"},
        env,
    )
    assert _write_tool(session, outside, env).get("permissionDecision") != "deny"
    pending_path = _pending_file(tmp_path)
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending["literal_objective"] = "Tampered objective"
    pending_path.write_text(json.dumps(pending), encoding="utf-8")

    decision = _write_tool(session, outside, env)
    assert decision["permissionDecision"] == "deny"
    assert "pending startup objective is invalid" in decision["permissionDecisionReason"]
