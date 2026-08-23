"""Focused tests for clear disclosure and quarantine."""

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


def _project_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_id: str
) -> tuple[dict[str, str], list[Path], Path]:
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}
    handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Frozen project objective",
        },
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    return base, roots, setup_driver_module._state_path(project.resolve(), session_id)


def _write_tampered_pending(session_id: str) -> Path:
    pending_path = setup_driver_module._pending_state_path(session_id)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(
        json.dumps(
            {
                "session_key": setup_driver_module._session_key(session_id),
                "literal_objective": "tampered",
                "surface": "codex",
                "recorded_at_ns": 1,
                "pending_seal": "sha256-hmac:deadbeef",
            }
        ),
        encoding="utf-8",
    )
    return pending_path


def _record_pending(tmp_path: Path, session_id: str) -> Path:
    outside = tmp_path / "outside-any-checkout"
    outside.mkdir()
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    return setup_driver_module._pending_state_path(session_id)


def _submit(base: dict[str, str], roots: list[Path], prompt: str) -> dict:
    return handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": prompt},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )


def _clear(base: dict[str, str], roots: list[Path]) -> None:
    handle_hook(
        {**base, "hook_event_name": "SessionStart", "source": "clear"},
        surface="codex",
        event="SessionStart",
        skill_search_roots=roots,
    )


def test_quarantine_refusal_also_discloses_that_clear_discards_both_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every refusal naming source=clear must disclose what it destroys."""
    session_id = "quarantine-discloses-both"
    base, roots, state_path = _project_session(tmp_path, monkeypatch, session_id)
    pending_path = _write_tampered_pending(session_id)
    denied = _submit(base, roots, "a later subordinate prompt")
    reason = denied["reason"]
    assert "invalid" in reason
    assert "DISCARDS BOTH" in reason, "the quarantine refusal must not understate clear"
    assert "receipt" in reason

    assert state_path.is_file() and pending_path.is_file()
    _clear(base, roots)
    assert not state_path.is_file(), "clear removes the frozen project state too"
    assert not pending_path.is_file(), "clear removes the pending record"


def test_refusal_discloses_that_clear_discards_both_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stated operator exit must disclose that it destroys both records."""
    session_id = "clear-discloses-both"
    base, roots, state_path = _project_session(tmp_path, monkeypatch, session_id)
    pending_path = _record_pending(tmp_path, session_id)
    blocked = _submit(base, roots, "a later subordinate prompt")
    reason = blocked["reason"]
    assert "DISCARDS BOTH" in reason
    assert "pending" in reason and "receipt" in reason

    assert state_path.is_file() and pending_path.is_file()
    _clear(base, roots)
    assert not state_path.is_file(), "clear removes the project state too"
    assert not pending_path.is_file(), "clear removes the pending record"
