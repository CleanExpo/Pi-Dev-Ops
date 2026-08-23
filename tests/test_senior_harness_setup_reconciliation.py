"""Focused tests for clock and tamper reconciliation."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _init_repo,
    handle_hook,
    json,
    pytest,
    setup_driver_module,
)


def _project_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_id: str,
    project_name: str = "live-project",
) -> tuple[Path, dict[str, str], list[Path]]:
    project = tmp_path / project_name
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    return (
        project,
        {"session_id": session_id, "cwd": str(project)},
        [REPO_ROOT / "skills"],
    )


def _submit(base: dict[str, str], roots: list[Path], prompt: str) -> dict:
    return handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": prompt},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )


def _record_pending(tmp_path: Path, session_id: str, prompt: str) -> Path:
    outside = tmp_path / "outside-any-checkout"
    outside.mkdir(exist_ok=True)
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    return setup_driver_module._pending_state_path(session_id)


def _write_invalid_pending(session_id: str) -> Path:
    pending_path = setup_driver_module._pending_state_path(session_id)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(
        json.dumps(
            {
                "session_key": setup_driver_module._session_key(session_id),
                "literal_objective": "Injected objective",
                "surface": "codex",
                "pending_seal": "sha256-hmac:" + "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    return pending_path


def test_clock_rollback_between_writes_cannot_delete_the_later_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wall-clock samples are not chronology and cannot authorise deletion."""
    session_id = "clock-rollback"
    _, base, roots = _project_context(tmp_path, monkeypatch, session_id)

    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 200)
    _submit(base, roots, "Older admitted objective")

    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 100)
    pending_path = _record_pending(tmp_path, session_id, "Later pending objective")
    assert pending_path.is_file()
    _submit(base, roots, "a later subordinate prompt")

    assert pending_path.is_file(), (
        "a backwards clock adjustment must never delete the later sealed objective"
    )
    survived = json.loads(pending_path.read_text(encoding="utf-8"))
    assert survived["literal_objective"] == "Later pending objective"


def test_tampered_outer_admission_stamp_cannot_retire_a_newer_pending_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordering evidence must live under the seal, not beside it."""
    session_id = "outer-stamp-tamper"
    project, base, roots = _project_context(tmp_path, monkeypatch, session_id)
    _submit(base, roots, "Older admitted objective")
    state_path = setup_driver_module._state_path(project.resolve(), session_id)
    pending_path = _record_pending(tmp_path, session_id, "Later pending objective")
    sealed_pending = json.loads(pending_path.read_text(encoding="utf-8"))

    state = json.loads(state_path.read_text(encoding="utf-8"))
    sealed_receipt_before = json.dumps(state["receipt"], sort_keys=True)
    state["admitted_at_ns"] = sealed_pending["recorded_at_ns"] + 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert (
        json.dumps(
            json.loads(state_path.read_text(encoding="utf-8"))["receipt"],
            sort_keys=True,
        )
        == sealed_receipt_before
    ), "the receipt itself must be unchanged by this tamper"

    _submit(base, roots, "a later subordinate prompt")

    assert pending_path.is_file(), (
        "a forged outer admission stamp must not retire the newer sealed objective"
    )
    survived = json.loads(pending_path.read_text(encoding="utf-8"))
    assert survived["literal_objective"] == "Later pending objective"


def test_even_a_genuinely_older_sealed_record_is_preserved_not_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even apparently ordered records require explicit operator retirement."""
    session_id = "ordered-pending-session"
    project, base, roots = _project_context(tmp_path, monkeypatch, session_id)
    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 100)
    pending_path = _record_pending(
        tmp_path, session_id, "Genuinely earlier pending objective"
    )
    sealed = json.loads(pending_path.read_text(encoding="utf-8"))

    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 200)
    _submit(base, roots, "Objective admitted here")
    state_path = setup_driver_module._state_path(project.resolve(), session_id)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert sealed["recorded_at_ns"] < state["receipt"]["admission_order_ns"]
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(sealed), encoding="utf-8")

    blocked = _submit(base, roots, "a later subordinate prompt")

    assert pending_path.is_file(), "no sealed objective may be destroyed automatically"
    assert blocked["decision"] == "block"
    assert "order cannot be established" in blocked["reason"]
    assert "NOT authoritative" in blocked["reason"]


def test_tampered_pending_record_still_quarantines_after_a_valid_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tampered pending record must not become a laundering route."""
    session_id = "quarantine-session"
    _, base, roots = _project_context(
        tmp_path, monkeypatch, session_id, project_name="quarantine-project"
    )
    _submit(base, roots, "Live objective for this project")
    pending_path = _write_invalid_pending(session_id)

    denied = _submit(base, roots, "a later prompt")
    assert denied["decision"] == "block"
    assert "pending startup objective is invalid" in denied["reason"]
    assert pending_path.is_file()
