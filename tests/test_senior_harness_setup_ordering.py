"""Focused tests for objective ordering refusal."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _init_repo,
    digest,
    handle_hook,
    json,
    pytest,
    setup_driver_module,
)


def _project_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_id: str
) -> tuple[Path, dict[str, str], list[Path]]:
    project = tmp_path / "live-project"
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


def _record_pending(location: Path, session_id: str, prompt: str) -> Path:
    location.mkdir(exist_ok=True)
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(location),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    return setup_driver_module._pending_state_path(session_id)


def _remove_order_stamp(drop: str, state_path: Path, pending_path: Path) -> None:
    if drop == "admitted_at_ns":
        state = json.loads(state_path.read_text(encoding="utf-8"))
        receipt = state["receipt"]
        assert receipt.pop("admission_order_ns", None) is not None
        receipt.pop("receipt_integrity_digest", None)
        receipt.pop("receipt_seal", None)
        receipt["receipt_integrity_digest"] = digest(receipt)
        receipt["receipt_seal"] = setup_driver_module._receipt_seal(receipt)
        state_path.write_text(json.dumps(state), encoding="utf-8")
    else:
        sealed = json.loads(pending_path.read_text(encoding="utf-8"))
        sealed.pop("recorded_at_ns", None)
        sealed["pending_seal"] = setup_driver_module._pending_objective_seal(sealed)
        pending_path.write_text(json.dumps(sealed), encoding="utf-8")


def test_review_later_pending_objective_is_not_discarded_by_older_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt proves integrity, never chronology or safe retirement."""
    session_id = "orphaned-pending-session"
    project, base, roots = _project_context(tmp_path, monkeypatch, session_id)
    _submit(base, roots, "Older admitted objective")
    state_path = setup_driver_module._state_path(project.resolve(), session_id)
    assert state_path.is_file()

    outside = tmp_path / "outside-any-checkout"
    pending_path = _record_pending(outside, session_id, "Later pending objective")
    assert pending_path.is_file()
    blocked = _submit(base, roots, "a later subordinate prompt")

    assert pending_path.is_file()
    sealed = json.loads(pending_path.read_text(encoding="utf-8"))
    assert sealed["literal_objective"] == "Later pending objective"
    assert blocked["decision"] == "block"
    reason = blocked["reason"]
    assert reason == blocked["hookSpecificOutput"]["additionalContext"]
    assert "order cannot be established" in reason
    assert "Later pending objective" in reason
    assert "Older admitted objective" in reason
    assert "was retired" not in reason


@pytest.mark.parametrize("drop", ["admitted_at_ns", "recorded_at_ns"])
def test_unstamped_state_or_pending_record_blocks_instead_of_retiring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drop: str
) -> None:
    """An absent order stamp must block rather than silently retire state."""
    session_id = f"legacy-stamp-{drop}"
    project, base, roots = _project_context(tmp_path, monkeypatch, session_id)
    _submit(base, roots, "Admitted objective")
    state_path = setup_driver_module._state_path(project.resolve(), session_id)
    pending_path = _record_pending(tmp_path, session_id, "Pending objective")
    _remove_order_stamp(drop, state_path, pending_path)
    blocked = _submit(base, roots, "a later subordinate prompt")
    assert pending_path.is_file(), "an unstamped record must never be destroyed"
    assert blocked["decision"] == "block"
    assert "order cannot be established" in blocked["reason"]
