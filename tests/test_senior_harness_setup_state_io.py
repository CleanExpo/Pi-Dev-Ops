"""Focused tests for atomic state publication."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    json,
    pytest,
    setup_driver_module,
    stat,
)


def test_write_state_uses_a_temporary_path_unique_to_each_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.json"
    observed: list[Path] = []
    real_replace = Path.replace

    def recording_replace(self: Path, other) -> None:
        observed.append(Path(self))
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", recording_replace)
    setup_driver_module._write_state(target, {"writer": "a"})
    setup_driver_module._write_state(target, {"writer": "b"})

    assert len(observed) == 2
    assert observed[0] != observed[1]
    assert target.with_suffix(".tmp") not in observed


def test_concurrent_writers_cannot_publish_each_others_session_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interleave two writers in the exact window a shared temp name makes fatal.

    Claude and Codex PreToolUse matchers fire on every tool, so a second hook process
    can complete a whole write between the first writer's temp write and its replace.
    With one fixed sibling ``.tmp`` the second writer overwrites and then consumes the
    first writer's temp file, so the first replace fails outright.
    """
    target = tmp_path / "session.json"
    real_replace = Path.replace
    interleaved = {"done": False}

    def interleaving_replace(self: Path, other) -> None:
        if not interleaved["done"]:
            interleaved["done"] = True
            setup_driver_module._write_state(target, {"writer": "b"})
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", interleaving_replace)
    setup_driver_module._write_state(target, {"writer": "a"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"writer": "a"}
    assert not list(tmp_path.glob("*.tmp"))
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
