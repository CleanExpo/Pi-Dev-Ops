"""Release evidence must survive restarts without inventing old approvals."""
from unittest.mock import Mock

import pytest


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    from app.server import config, session_model, supabase_log

    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(session_model, "_sessions", {})
    monkeypatch.setattr(supabase_log, "_upsert", Mock(return_value=True))
    return session_model, supabase_log


def test_release_evidence_survives_disk_restore_and_api(isolated_store):
    from app.server import persistence

    model, supabase = isolated_store
    session = model.BuildSession(id="evidence1", status="blocked")
    evidence = {
        "base_sha": "a" * 40,
        "candidate_sha": "b" * 40,
        "verified_sha": "b" * 40,
        "verification": {"passed": False, "checks": [{"exit_code": 1}]},
        "audit_evidence": [{"provider": "openai", "verdict": "BLOCK"}],
        "adversary_verdict": {"verdict": "BLOCK"},
    }
    for key, value in evidence.items():
        setattr(session, key, value)
    persistence.save_session(session)
    checkpoint = supabase._upsert.call_args.args[1]["checkpoint"]
    model.restore_sessions()
    restored = model.get_session(session.id)
    api_row = model.list_sessions()[0]
    for key, value in evidence.items():
        assert checkpoint[key] == value
        assert getattr(restored, key) == value
        assert api_row[key] == value


def test_old_checkpoint_does_not_inherit_release_proof(isolated_store, monkeypatch):
    from app.server import persistence

    model, _ = isolated_store
    monkeypatch.setattr(persistence, "load_all_sessions", lambda: [{"id": "legacy", "status": "complete"}])
    model.restore_sessions()
    session = model.get_session("legacy")
    assert session.verified_sha == ""
    assert session.verification == {}
    assert session.audit_evidence == []


def test_inflight_evaluation_is_interrupted_after_restart(isolated_store, monkeypatch):
    from app.server import persistence

    model, _ = isolated_store
    monkeypatch.setattr(persistence, "load_all_sessions", lambda: [{"id": "evaluating1", "status": "evaluating"}])
    model.restore_sessions()
    assert model.get_session("evaluating1").status == "interrupted"


@pytest.mark.parametrize("same_host", [True, False])
def test_checkpoint_recovery_keeps_only_locally_reusable_evidence(monkeypatch, same_host):
    from app.server import session_lease, session_recovery
    monkeypatch.setattr(session_lease, "local_host", lambda: "current")
    checkpoint = {"host": "current" if same_host else "previous", "workspace": "/candidate",
                  "last_completed_phase": "generator", "base_sha": "a" * 40,
                  "candidate_sha": "b" * 40, "verified_sha": "b" * 40,
                  "verification": {"status": "passed"}, "audit_evidence": [{"rc": 0}],
                  "adversary_verdict": {"verdict": "APPROVE"}}
    restored = session_recovery.session_from_checkpoint("resume", {}, checkpoint)
    assert restored.candidate_sha == ("b" * 40 if same_host else "")
    assert restored.audit_evidence == ([{"rc": 0}] if same_host else [])
    assert restored.verification == ({"status": "passed"} if same_host else {})
    assert session_recovery.resume_target(checkpoint, "generator")[1] == (
        "generator" if same_host else "claude_check")
