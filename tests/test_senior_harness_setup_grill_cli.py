"""Focused tests for Grill command classification."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    SCRIPT_DIR,
    _grill_command,
    _tamper_env,
    json,
    os,
    setup_driver_module,
    start_session,
    subprocess,
    sys,
)


def _grill_state(tmp_path: Path) -> tuple[Path, dict[str, str], bytes]:
    sketch = tmp_path / "Sketches" / "01-recovery.md"
    sketch.parent.mkdir(parents=True)
    sketch.write_text("# Recovery\n", encoding="utf-8")
    session = start_session(
        "Shape the recovery",
        sketch,
        [
            {
                "leaf_id": "market",
                "kind": "human-decision",
                "depends_on": [],
                "question": "Which market ships first?",
                "recommendation": "Start with the internal proving ground.",
                "rationale": "It produces evidence before external commitments.",
            }
        ],
        materialization_path=sketch.parent.parent / "Grills" / "01-recovery.md",
    )
    control_root = tmp_path / "state"
    control_root.mkdir()
    env = dict(os.environ, SENIOR_HARNESS_STATE_DIR=str(control_root))
    state_path = control_root / "grill-state.json"
    state_path.write_text(
        json.dumps(session, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return state_path, env, state_path.read_bytes()


def _run_grill(
    command: str, state_path: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    arguments = list(args)
    if command in {"evidence", "answer", "confirm", "materialize"}:
        integrity = json.loads(state_path.read_text(encoding="utf-8"))[
            "session_integrity_digest"
        ]
        arguments.extend(["--expected-integrity", integrity])
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "grill_session.py"),
            command,
            "--state",
            str(state_path),
            *arguments,
        ],
        env=env,
        capture_output=True,
        text=True,
    )


def test_recovery_without_receipt_denies_all_shell_grill_subcommands() -> None:
    for command in sorted(setup_driver_module.GRILL_READ_ONLY_COMMANDS):
        payload = _grill_command(command, "--state", "/tmp/grill-state.json")
        assert setup_driver_module._tool_is_recovery_safe(payload) is False, command


def test_recovery_read_denies_every_state_writing_grill_subcommand() -> None:
    for command in ("start", "evidence", "answer", "confirm", "materialize"):
        payload = _grill_command(command, "--state", "/tmp/grill-state.json")
        assert setup_driver_module._tool_is_recovery_safe(payload) is False, command
    # A bare invocation and an unrecognised subcommand are denied by omission.
    assert setup_driver_module._tool_is_recovery_safe(_grill_command()) is False
    assert setup_driver_module._tool_is_recovery_safe(_grill_command("purge")) is False


def test_grill_read_only_allowlist_tracks_the_grill_cli(tmp_path: Path) -> None:
    """Every shipped subcommand is classified, and new ones are denied by default."""
    import argparse

    import grill_session as grill_session_module

    subparsers = [
        action
        for action in grill_session_module._parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers) == 1
    shipped = set(subparsers[0].choices)
    assert setup_driver_module.GRILL_READ_ONLY_COMMANDS <= shipped
    for command in sorted(shipped - setup_driver_module.GRILL_READ_ONLY_COMMANDS):
        assert (
            setup_driver_module._tool_is_recovery_safe(_grill_command(command)) is False
        ), command


def test_allowlisted_grill_subcommands_do_not_write_state_but_denied_ones_do(
    tmp_path: Path,
) -> None:
    """Prove the classification against the real CLI rather than trusting its name."""
    state_path, env, before = _grill_state(tmp_path)

    for command in sorted(setup_driver_module.GRILL_READ_ONLY_COMMANDS):
        result = _run_grill(command, state_path, env)
        assert result.returncode == 0, (command, result.stderr)
        assert state_path.read_bytes() == before, command

    answered = _run_grill(
        "answer",
        state_path,
        env,
        "--answer",
        "Internal proving ground first.",
        "--resolution",
        "DECIDED",
    )
    assert answered.returncode == 0, answered.stderr
    assert state_path.read_bytes() != before


def test_concurrent_answers_use_compare_and_swap(
    tmp_path: Path,
) -> None:
    state_path, env, _before = _grill_state(tmp_path)
    integrity = json.loads(state_path.read_text(encoding="utf-8"))[
        "session_integrity_digest"
    ]
    base = [
        sys.executable, str(SCRIPT_DIR / "grill_session.py"), "answer",
        "--state", str(state_path), "--resolution", "DECIDED",
        "--expected-integrity", integrity, "--answer",
    ]
    processes = [
        subprocess.Popen([*base, answer], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
        for answer in ("Market A", "Market B")
    ]
    results = [process.communicate(timeout=10) for process in processes]
    returncodes = [process.returncode for process in processes]
    assert sorted(returncodes) == [0, 2], results
    loser_error = results[returncodes.index(2)][1]
    assert "state changed after it was observed" in loser_error


def test_grill_cli_rejects_abbreviated_state_option(
    tmp_path: Path,
) -> None:
    state_path, env, before = _grill_state(tmp_path)
    other = tmp_path / "other.json"
    grill = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "grill_session.py"),
            "show",
            "--state",
            str(state_path),
            "--sta",
            str(other),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert grill.returncode == 2
    assert "unrecognized arguments: --sta" in grill.stderr
    assert state_path.read_bytes() == before


def test_guard_cli_rejects_abbreviated_session_option(tmp_path: Path) -> None:
    state_path, env, _before = _grill_state(tmp_path)
    other = tmp_path / "other.json"
    guard = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "guard-dispatch",
            str(tmp_path / "contract.json"),
            str(tmp_path / "receipt.json"),
            "--move-id",
            "M07",
            "--grill-session",
            str(state_path),
            "--gr",
            str(other),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert guard.returncode == 2
    assert "unrecognized arguments: --gr" in guard.stderr


def test_recovery_read_denies_a_grill_write_when_no_receipt_exists(
    tmp_path: Path,
) -> None:
    env = _tamper_env(tmp_path)
    for command in ("show", "materialize"):
        payload = _grill_command(command, "--state", str(tmp_path / "grill-state.json"))
        payload["session_id"] = f"no-receipt-{command}"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "setup_driver.py"),
                "hook",
                "--surface",
                "claude",
                "--event",
                "PreToolUse",
            ],
            input=json.dumps(payload),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert output["permissionDecision"] == "deny", command
        assert "no startup receipt exists" in output["permissionDecisionReason"]
