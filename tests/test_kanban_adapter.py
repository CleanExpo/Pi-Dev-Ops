"""tests/test_kanban_adapter.py — RA-1865 (B2) Kanban subprocess adapter smoke.

The hermes binary is patched in-place so tests don't need a live Hermes
installation. We assert the constructed argv shapes + parse logic.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import kanban_adapter as KA  # noqa: E402
from conftest import assert_kanban_environment_isolated  # noqa: E402


def test_pytest_process_uses_isolated_kanban_environment():
    """Hostile worker env must be replaced before any test can emit a card."""
    root = Path(os.environ["PI_DEV_TEST_KANBAN_ROOT"]).resolve()
    database = Path(os.environ["HERMES_KANBAN_DB"]).resolve()

    assert database.is_relative_to(root)
    assert os.environ["HERMES_KANBAN_BOARD"] == "pi-dev-ops-pytest"
    assert os.environ["HERMES_TENANT"] == "pi-dev-ops-pytest"
    assert "HERMES_KANBAN_TASK" not in os.environ
    assert "HERMES_KANBAN_RUN_ID" not in os.environ


def test_kanban_guard_rejects_database_outside_test_root(monkeypatch, tmp_path):
    escaped_database = tmp_path.parent / "escaped-kanban.db"
    with monkeypatch.context() as env:
        env.setenv("HERMES_KANBAN_DB", str(escaped_database))
        with pytest.raises(AssertionError, match="escaped private root"):
            assert_kanban_environment_isolated()


def test_kanban_guard_rejects_changed_test_root(monkeypatch):
    private_root = Path(os.environ["PI_DEV_TEST_KANBAN_ROOT"]).resolve()
    with monkeypatch.context() as env:
        env.setenv("PI_DEV_TEST_KANBAN_ROOT", str(private_root.parent))
        with pytest.raises(AssertionError, match="test root pin was changed"):
            assert_kanban_environment_isolated()


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("HERMES_KANBAN_HOME", "Kanban test home pin was changed"),
        ("HERMES_KANBAN_WORKSPACES_ROOT", "Kanban test workspaces pin was changed"),
    ],
)
def test_kanban_guard_rejects_changed_support_path(monkeypatch, key, message):
    private_root = Path(os.environ["PI_DEV_TEST_KANBAN_ROOT"]).resolve()
    with monkeypatch.context() as env:
        env.setenv(key, str(private_root.parent))
        with pytest.raises(AssertionError, match=message):
            assert_kanban_environment_isolated()


def _patch_run(monkeypatch, *, rc: int = 0, stdout: str = "",
                stderr: str = "", record: list | None = None):
    """Replace KA._run with a recorder. record gets (args, ...)."""
    def fake_run(args, timeout_s=KA.HERMES_TIMEOUT_S):
        if record is not None:
            record.append((tuple(args), timeout_s))
        return rc, stdout, stderr
    monkeypatch.setattr(KA, "_run", fake_run)


# ── _hermes_bin / _run guards ───────────────────────────────────────────────


def test_hermes_bin_none_returns_127(monkeypatch):
    """Without hermes on PATH, _run reports rc=127 cleanly."""
    monkeypatch.setattr(KA, "_hermes_bin", lambda: None)
    rc, out, err = KA._run(["kanban", "list"])
    assert rc == 127
    assert out == ""
    assert "not on PATH" in err


# ── create_card ──────────────────────────────────────────────────────────────


def test_create_card_argv_shape(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, stdout='{"task_id": "k-abc1"}', record=record)
    out = KA.create_card(
        title="hello", body="world",
        tenant="pi-ceo", priority=5,
        idempotency_key="dedup-1",
        parent_ids=["k-parent"],
        skills=["debate-summary"],
    )
    assert out == "k-abc1"
    args, _ = record[0]
    assert args[:3] == ("kanban", "create", "--json")
    assert "--body" in args and "world" in args
    assert "--tenant" in args and "pi-ceo" in args
    assert "--priority" in args and "5" in args
    assert "--idempotency-key" in args and "dedup-1" in args
    assert "--parent" in args and "k-parent" in args
    assert "--skill" in args and "debate-summary" in args
    # Title is the last positional
    assert args[-1] == "hello"


def test_create_card_with_board_argv_shape(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, stdout='{"task_id": "k-board1"}', record=record)
    out = KA.create_card(
        title="voice card",
        body="from crm",
        tenant="pi-ceo",
        board="unite-group-portfolio-ops",
    )
    assert out == "k-board1"
    args, _ = record[0]
    assert args[:4] == ("kanban", "--board", "unite-group-portfolio-ops", "create")
    assert "--json" in args
    assert args[-1] == "voice card"


def test_create_card_failure_returns_none(monkeypatch):
    _patch_run(monkeypatch, rc=1, stdout="", stderr="db locked")
    assert KA.create_card(title="x") is None


def test_create_card_no_taskid_in_output(monkeypatch):
    _patch_run(monkeypatch, rc=0, stdout="ok")
    # No task_id parseable — should return None but not crash
    assert KA.create_card(title="x") is None


def test_parse_create_id_from_json():
    assert KA._parse_create_id('{"task_id": "k-001"}') == "k-001"
    assert KA._parse_create_id('{"id": "k-002"}') == "k-002"


def test_parse_create_id_from_plain():
    assert KA._parse_create_id("created k-abc999 ok") == "k-abc999"


def test_parse_create_id_empty():
    assert KA._parse_create_id("") is None
    assert KA._parse_create_id("no kanban id here") is None


# ── add_comment ──────────────────────────────────────────────────────────────


def test_add_comment_success(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, record=record)
    assert KA.add_comment(task_id="k-1", text="hello", author="cfo") is True
    args, _ = record[0]
    assert args[0] == "kanban" and args[1] == "comment"
    assert "--author" in args and "cfo" in args
    assert "k-1" in args
    assert "hello" in args


def test_add_comment_failure(monkeypatch):
    _patch_run(monkeypatch, rc=1, stderr="not found")
    assert KA.add_comment(task_id="k-1", text="x") is False


# ── complete_card / block_card ──────────────────────────────────────────────


def test_complete_card_argv(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, record=record)
    assert KA.complete_card(
        task_id="k-1", summary="done", result="ok",
    ) is True
    args, _ = record[0]
    assert "complete" in args
    assert "--summary" in args and "done" in args
    assert "--result" in args and "ok" in args
    assert "k-1" in args


def test_block_card(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, record=record)
    assert KA.block_card(task_id="k-1") is True
    args, _ = record[0]
    assert args == ("kanban", "block", "k-1")


# ── list_open ───────────────────────────────────────────────────────────────


def test_list_open_parses_json(monkeypatch):
    payload = (
        '[{"task_id": "k-1", "title": "t1", "status": "ready", '
        '"assignee": "cfo", "tenant": "pi-ceo", "parent_ids": [], '
        '"body": "b1"}, '
        '{"task_id": "k-2", "title": "t2", "status": "running", '
        '"assignee": null, "tenant": "pi-ceo", "parent_ids": ["k-1"], '
        '"body": null}]'
    )
    _patch_run(monkeypatch, rc=0, stdout=payload)
    cards = KA.list_open(tenant="pi-ceo")
    assert len(cards) == 2
    assert cards[0].task_id == "k-1" and cards[0].status == "ready"
    assert cards[1].task_id == "k-2" and cards[1].parent_ids == ["k-1"]


def test_list_open_handles_failure(monkeypatch):
    _patch_run(monkeypatch, rc=1, stderr="db locked")
    assert KA.list_open() == []


def test_list_open_handles_bad_json(monkeypatch):
    _patch_run(monkeypatch, rc=0, stdout="<not json>")
    assert KA.list_open() == []


# ── emit_debate_card ────────────────────────────────────────────────────────


def test_emit_debate_card_uses_debate_id_as_idempotency_key(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, stdout='{"task_id": "k-deb1"}',
               record=record)
    out = KA.emit_debate_card(
        role="CFO", business_id="restoreassist",
        topic="ship today's CFO brief",
        drafter_artifact="DRAFT", redteam_artifact="CRIT",
        debate_id="deb-xyz",
    )
    assert out == "k-deb1"
    args, _ = record[0]
    assert "--idempotency-key" in args and "deb-xyz" in args
    assert "--tenant" in args and "pi-ceo" in args
    # Title contains role + business_id
    title = args[-1]
    assert "[CFO@restoreassist]" in title
