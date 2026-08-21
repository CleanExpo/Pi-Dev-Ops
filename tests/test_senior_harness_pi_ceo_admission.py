"""Focused acceptance tests for Pi-CEO's non-authorizing Harness projection."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server import persistence, session_model, sessions, supabase_log
from app.server.auth import require_auth, require_rate_limit
from app.server.senior_harness_admission import (
    MODE_ENV,
    SeniorHarnessAdmissionUnavailable,
    api_projection,
    observe,
)


def _reservation(**updates):
    value = {
        "schema_version": "1.0",
        "reservation_ref": "reservation-1",
        "task_id": "task-1",
        "plan_id": "plan-1",
        "node_id": "1.1",
        "worker_id": "worker-a",
        "worker_context_id": "context-a",
        "base_sha": "a" * 40,
        "node_contract_digest": "b" * 64,
    }
    value.update(updates)
    return value


@pytest.fixture(autouse=True)
def _reset_sessions(monkeypatch):
    monkeypatch.delenv(MODE_ENV, raising=False)
    saved = dict(session_model._sessions)
    session_model._sessions.clear()
    yield
    session_model._sessions.clear()
    session_model._sessions.update(saved)


def _client():
    from app.server.routes.sessions import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app, raise_server_exceptions=True)


def test_off_is_default_and_discards_caller_projection():
    status, admission_ref, reservation = observe("admission-1", _reservation())
    assert (status, admission_ref, reservation) == ("off", None, None)


def test_observe_deep_copies_complete_closed_projection(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "observe")
    raw = _reservation()

    status, admission_ref, reservation = observe("admission-1", raw)
    raw["plan_id"] = "mutated"

    assert status == "observed"
    assert admission_ref == "admission-1"
    assert reservation["plan_id"] == "plan-1"
    assert reservation is not raw


@pytest.mark.parametrize(
    "admission_ref,reservation",
    [
        (None, None),
        ("admission-1", None),
        (None, _reservation()),
        ("admission-1", _reservation(authority="trusted")),
        ("admission-1", _reservation(authority_mac="secret")),
        ("admission-1", _reservation(schema_version="2.0")),
        ("admission-1", _reservation(plan_id={"nested": "payload"})),
    ],
)
def test_observe_never_promotes_missing_or_malformed_input(
    monkeypatch, admission_ref, reservation,
):
    monkeypatch.setenv(MODE_ENV, "observe")

    status, safe_ref, safe_reservation = observe(admission_ref, reservation)

    expected = "missing" if admission_ref is None and reservation is None else "malformed"
    assert (status, safe_ref, safe_reservation) == (expected, None, None)


@pytest.mark.asyncio
async def test_create_session_observes_and_defensively_copies(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "observe")
    raw = _reservation()
    monkeypatch.setattr(sessions.persistence, "save_session", lambda _session: None)

    with patch.object(sessions.asyncio, "create_task") as create_task:
        create_task.side_effect = lambda coro: coro.close()
        created = await sessions.create_session(
            "https://github.com/org/repo",
            senior_harness_admission_ref="admission-1",
            senior_harness_reservation=raw,
        )

    raw["node_id"] = "changed"
    assert created.senior_harness_observation_status == "observed"
    assert created.senior_harness_reservation["node_id"] == "1.1"


@pytest.mark.asyncio
async def test_enforce_denies_creation_before_any_side_effect(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "enforce")

    with patch.object(sessions, "_reconcile_stale_terminal_sessions") as reconcile, \
         patch.object(sessions.persistence, "save_session") as save, \
         patch.object(sessions.asyncio, "create_task") as create_task:
        with pytest.raises(SeniorHarnessAdmissionUnavailable):
            await sessions.create_session("https://github.com/org/repo")

    assert session_model._sessions == {}
    reconcile.assert_not_called()
    save.assert_not_called()
    create_task.assert_not_called()


def test_local_json_round_trip_preserves_only_safe_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path))
    session = session_model.BuildSession(
        id="safe-session",
        repo_url="https://github.com/org/repo",
        senior_harness_observation_status="observed",
        senior_harness_admission_ref="admission-1",
        senior_harness_reservation=_reservation(),
    )

    with patch.object(supabase_log, "save_session_checkpoint", return_value=True):
        persistence.save_session(session)

    payload = json.loads(Path(persistence._path(session.id)).read_text(encoding="utf-8"))
    assert payload["senior_harness_reservation"] == _reservation()
    serialized = json.dumps(payload)
    assert "authority" not in serialized
    assert "authority_mac" not in serialized


def test_persistence_boundaries_drop_tampered_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path))
    session = session_model.BuildSession(
        id="tampered-session",
        repo_url="https://github.com/org/repo",
        senior_harness_observation_status="observed",
        senior_harness_admission_ref="admission-1",
        senior_harness_reservation=_reservation(authority_mac="secret"),
    )
    captured = {}
    with patch.object(
        supabase_log,
        "_upsert",
        side_effect=lambda table, row: captured.update(table=table, row=row) or True,
    ):
        persistence.save_session(session)

    local = json.loads(Path(persistence._path(session.id)).read_text(encoding="utf-8"))
    assert local["senior_harness_observation_status"] == "malformed"
    assert local["senior_harness_admission_ref"] is None
    assert local["senior_harness_reservation"] is None
    checkpoint = captured["row"]["checkpoint"]
    assert checkpoint["senior_harness_observation_status"] == "malformed"
    assert checkpoint["senior_harness_admission_ref"] is None
    assert checkpoint["senior_harness_reservation"] is None


def test_local_restore_revalidates_projection(monkeypatch):
    stored = {
        "id": "restored-session",
        "repo_url": "https://github.com/org/repo",
        "status": "done",
        "senior_harness_observation_status": "observed",
        "senior_harness_admission_ref": "admission-1",
        "senior_harness_reservation": _reservation(authority_mac="secret"),
    }
    monkeypatch.setattr(session_model.persistence, "load_all_sessions", lambda: [stored])

    session_model.restore_sessions()

    restored = session_model._sessions["restored-session"]
    assert restored.senior_harness_observation_status == "malformed"
    assert restored.senior_harness_admission_ref is None
    assert restored.senior_harness_reservation is None


def test_enforce_restores_only_inert_interrupted_metadata(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "enforce")
    stored = {
        "id": "restored-enforce",
        "repo_url": "https://github.com/org/repo",
        "status": "building",
        "senior_harness_observation_status": "enforced",
        "senior_harness_admission_ref": "admission-1",
        "senior_harness_reservation": _reservation(),
    }
    with patch.object(session_model.persistence, "load_all_sessions", return_value=[stored]), \
         patch.object(session_model.persistence, "save_session") as save:
        session_model.restore_sessions()

    restored = session_model._sessions["restored-enforce"]
    assert restored.status == "interrupted"
    assert restored.senior_harness_observation_status == "observed"
    save.assert_called_once_with(restored)


def test_supabase_checkpoint_and_recovery_preserve_safe_projection(monkeypatch):
    original = session_model.BuildSession(
        id="supabase-session",
        repo_url="https://github.com/org/repo",
        status="interrupted",
        last_completed_phase="generate",
        senior_harness_observation_status="observed",
        senior_harness_admission_ref="admission-1",
        senior_harness_reservation=_reservation(),
    )
    captured = {}
    with patch.object(
        supabase_log,
        "_upsert",
        side_effect=lambda table, row: captured.update(table=table, row=row) or True,
    ):
        assert supabase_log.save_session_checkpoint(original) is True

    checkpoint = captured["row"]["checkpoint"]
    assert checkpoint["senior_harness_reservation"] == _reservation()
    rows = [{
        "id": original.id,
        "repo_url": original.repo_url,
        "status": "interrupted",
        "checkpoint": checkpoint,
    }]
    with patch.object(supabase_log, "fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=AsyncMock()), \
         patch.object(session_model.persistence, "save_session", lambda _session: None), \
         patch.object(session_model.asyncio, "create_task") as create_task:
        create_task.side_effect = lambda coro: coro.close()
        assert session_model.recover_interrupted_sessions_from_supabase(max_concurrent=1) == 1

    recovered = session_model._sessions[original.id]
    assert recovered.senior_harness_observation_status == "observed"
    assert recovered.senior_harness_reservation == _reservation()


def test_enforce_skips_supabase_auto_recovery_before_fetch_insert_or_schedule(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "enforce")
    with patch.object(supabase_log, "fetch_interrupted_sessions") as fetch, \
         patch.object(session_model.persistence, "save_session") as save, \
         patch.object(session_model.asyncio, "create_task") as create_task:
        assert session_model.recover_interrupted_sessions_from_supabase() == 0

    assert session_model._sessions == {}
    fetch.assert_not_called()
    save.assert_not_called()
    create_task.assert_not_called()


def test_api_projection_is_sanitized_and_deep_copied():
    session = SimpleNamespace(
        senior_harness_observation_status="observed",
        senior_harness_admission_ref="admission-1",
        senior_harness_reservation=_reservation(),
    )

    projected = api_projection(session)
    projected["reservation"]["node_id"] = "mutated"

    assert session.senior_harness_reservation["node_id"] == "1.1"
    assert "authority" not in projected


@pytest.mark.parametrize(
    "harness_fields",
    [
        {"senior_harness_admission_ref": "admission-1"},
        {"senior_harness_reservation": _reservation()},
        {
            "senior_harness_admission_ref": "admission-1",
            "senior_harness_reservation": _reservation(),
        },
    ],
)
def test_parallel_route_rejects_harness_projection_before_fan_out(
    monkeypatch, harness_fields,
):
    monkeypatch.setenv(MODE_ENV, "observe")
    with patch("app.server.routes.sessions.fan_out", new=AsyncMock()) as fan_out:
        response = _client().post(
            "/api/build/parallel",
            json={
                "repo_url": "https://github.com/org/repo",
                "brief": "parallel work",
                **harness_fields,
            },
        )

    assert response.status_code == 400
    fan_out.assert_not_called()


def test_build_route_forwards_and_returns_safe_observation(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "observe")

    async def fake_create(*_args, **kwargs):
        status, admission_ref, reservation = observe(
            kwargs["senior_harness_admission_ref"],
            kwargs["senior_harness_reservation"],
        )
        return session_model.BuildSession(
            id="route-session",
            status="created",
            senior_harness_observation_status=status,
            senior_harness_admission_ref=admission_ref,
            senior_harness_reservation=reservation,
        )

    with patch("app.server.routes.sessions.create_session", new=fake_create):
        response = _client().post(
            "/api/build",
            json={
                "repo_url": "https://github.com/org/repo",
                "senior_harness_admission_ref": "admission-1",
                "senior_harness_reservation": _reservation(),
                "senior_harness_mode": "enforce",
            },
        )

    assert response.status_code == 200
    assert response.json()["senior_harness"] == {
        "status": "observed",
        "admission_ref": "admission-1",
        "reservation": _reservation(),
    }


def test_build_route_surfaces_unavailable_enforce_as_503():
    with patch(
        "app.server.routes.sessions.create_session",
        new=AsyncMock(side_effect=SeniorHarnessAdmissionUnavailable("not installed")),
    ):
        response = _client().post(
            "/api/build",
            json={"repo_url": "https://github.com/org/repo"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "not installed"


@pytest.mark.asyncio
async def test_root_fan_out_enforce_denies_before_parent_or_clone(monkeypatch):
    from app.server import orchestrator

    monkeypatch.setenv(MODE_ENV, "enforce")
    with patch.object(orchestrator.os, "makedirs") as makedirs, \
         patch.object(orchestrator, "run_cmd", new=AsyncMock()) as run_cmd:
        with pytest.raises(SeniorHarnessAdmissionUnavailable):
            await orchestrator.fan_out("https://github.com/org/repo", "work")

    assert session_model._sessions == {}
    makedirs.assert_not_called()
    run_cmd.assert_not_called()
