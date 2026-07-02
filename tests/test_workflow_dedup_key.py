"""RA-6900 — CI workflow_run dedup uses stable sha256 keys, not hash()."""
from __future__ import annotations

from app.server.routes.webhooks import _load_dedup_set, _save_dedup_set, _workflow_dedup_key


def test_workflow_dedup_key_is_stable_across_calls():
    a = _workflow_dedup_key("CleanExpo/Pi-Dev-Ops", "abc123")
    b = _workflow_dedup_key("CleanExpo/Pi-Dev-Ops", "abc123")
    assert a == b
    assert len(a) == 64


def test_workflow_dedup_key_differs_by_sha():
    a = _workflow_dedup_key("CleanExpo/Pi-Dev-Ops", "abc123")
    b = _workflow_dedup_key("CleanExpo/Pi-Dev-Ops", "def456")
    assert a != b


def test_dedup_persist_roundtrip(tmp_path, monkeypatch):
    from app.server.routes import webhooks

    dedup_file = tmp_path / "dedup-run-ids.json"
    monkeypatch.setattr(webhooks, "_DEDUP_FILE", dedup_file)
    key = _workflow_dedup_key("org/repo", "sha")
    _save_dedup_set({key})
    loaded = _load_dedup_set()
    assert key in loaded
