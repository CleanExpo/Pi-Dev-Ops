"""Integrated Pi-CEO enforce-mode ingress and execution boundaries."""

from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.server import session_model, session_phases, sessions
from app.server.models import ResumeRequest
from app.server.routes.sessions import resume_session
from app.server.senior_harness_admission import (
    AdmissionVerificationError,
    ConsumerExpectation,
    MODE_ENV,
)
from app.server import senior_harness_consumer as consumer


def _authority_module():
    path = (
        Path(__file__).parents[1]
        / "skills/senior-harness/scripts/admission_authority.py"
    )
    name = "senior_harness_admission_authority_runtime_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AuthorityTransport:
    def __init__(self, authority, envelope):
        self.authority = authority
        self.envelope = copy.deepcopy(envelope)
        self.consume_calls: list[dict] = []
        self.assert_calls: list[dict] = []

    def _row(self):
        claim = self.envelope["claim"]
        expires = datetime.fromtimestamp(claim["expires_at"], tz=timezone.utc)
        return [{
            "admission_ref": claim["admission_ref"],
            "state": "consumed",
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "consumption_session_id": claim["session_id"],
        }]

    def consume_child(self, payload):
        self.consume_calls.append(copy.deepcopy(dict(payload)))
        claim = self.envelope["claim"]
        expectation = ConsumerExpectation(**{
            field: claim[field]
            for field in ConsumerExpectation.__dataclass_fields__
        })
        self.authority.consume_child(
            claim["admission_ref"],
            expectation=expectation,
            key_ring=self.authority.public_key_ring(),
        )
        return self._row()

    def assert_active(self, payload):
        self.assert_calls.append(copy.deepcopy(dict(payload)))
        claim = self.envelope["claim"]
        self.authority.assert_active(
            claim["admission_ref"], session_id=claim["session_id"]
        )
        return self._row()


@pytest.fixture
def admitted(monkeypatch):
    module = _authority_module()
    now = int(time.time())
    authority = module.InMemoryAdmissionAuthority(
        module.generate_private_key(),
        signer_key_id="issuer-runtime",
        audience="pi-ceo/build",
        clock=lambda: now,
    )
    brief = "Implement the exact admitted runtime"
    scope = {"paths": ["app/server/**"], "max_files_modified": 4}
    parent = authority.reserve_parent(
        source_kind="linear",
        source_id="issue-runtime",
        source_version="2026-08-21T09:00:00Z",
        repository="https://github.com/Unite-Group/Pi-Dev-Ops.git",
        objective=brief,
        scope=scope,
        task_id="task-runtime",
        plan_id="plan-runtime",
        base_sha="a" * 40,
        node_contract_digest="sha256:" + "b" * 64,
        ttl_seconds=600,
        admission_ref="parent-runtime",
    )
    envelope = authority.derive_child(
        parent["claim"]["admission_ref"],
        node_id="1.1",
        reservation_ref="reservation-runtime",
        worker_id="worker-runtime",
        worker_context_id="context-runtime",
        session_id="abcdef123456",
        node_contract_digest="sha256:" + "c" * 64,
        ttl_seconds=300,
        admission_ref="child-runtime",
    )
    reservation = {
        "schema_version": "1.0",
        "reservation_ref": "reservation-runtime",
        "task_id": "task-runtime",
        "plan_id": "plan-runtime",
        "node_id": "1.1",
        "worker_id": "worker-runtime",
        "worker_context_id": "context-runtime",
        "base_sha": "a" * 40,
        "node_contract_digest": "sha256:" + "c" * 64,
    }
    transport = AuthorityTransport(authority, envelope)
    consumer.install_runtime(transport, authority.public_key_ring(), "pi-ceo/build")
    monkeypatch.setenv(MODE_ENV, "enforce")
    saved_sessions = dict(session_model._sessions)
    session_model._sessions.clear()
    yield {
        "authority": authority,
        "transport": transport,
        "envelope": envelope,
        "brief": brief,
        "scope": scope,
        "reservation": reservation,
    }
    consumer.clear_runtime()
    session_model._sessions.clear()
    session_model._sessions.update(saved_sessions)


@pytest.mark.asyncio
async def test_create_consumes_before_memory_persistence_or_schedule(admitted):
    order: list[str] = []
    transport = admitted["transport"]
    original_consume = transport.consume_child

    def consume(payload):
        order.append("consume")
        return original_consume(payload)

    transport.consume_child = consume
    with patch.object(sessions.persistence, "save_session", side_effect=lambda _s: order.append("save")), \
         patch.object(sessions.asyncio, "create_task") as create_task:
        create_task.side_effect = lambda coro: (order.append("schedule"), coro.close())[-1]
        created = await sessions.create_session(
            "https://github.com/unite-group/pi-dev-ops.git",
            admitted["brief"],
            scope=admitted["scope"],
            senior_harness_admission_ref="child-runtime",
            senior_harness_reservation=admitted["reservation"],
            senior_harness_admission_envelope=admitted["envelope"],
        )

    assert created.id == "abcdef123456"
    assert created.senior_harness_observation_status == "enforced"
    assert order == ["consume", "save", "schedule"]
    assert "envelope" not in vars(created)
    assert "signature" not in repr(vars(created))


@pytest.mark.asyncio
async def test_invalid_create_fails_before_every_side_effect(admitted):
    with patch.object(sessions, "_reconcile_stale_terminal_sessions") as reconcile, \
         patch.object(sessions.persistence, "save_session") as save, \
         patch.object(sessions.asyncio, "create_task") as create_task:
        with pytest.raises(AdmissionVerificationError):
            await sessions.create_session(
                "https://github.com/unite-group/pi-dev-ops.git",
                admitted["brief"],
                scope=admitted["scope"],
                senior_harness_admission_ref="child-runtime",
                senior_harness_reservation=admitted["reservation"],
                senior_harness_admission_envelope=None,
            )

    assert session_model._sessions == {}
    assert admitted["transport"].consume_calls == []
    reconcile.assert_not_called()
    save.assert_not_called()
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_run_build_literal_first_operation_is_the_active_assertion(monkeypatch):
    tree = ast.parse(inspect.getsource(session_phases.run_build))
    function = tree.body[0]
    first = function.body[0]
    assert isinstance(first, ast.Expr)
    assert isinstance(first.value, ast.Call)
    assert first.value.func.id == "require_active_for_run"

    session = session_model.BuildSession(id="abcdef123456")
    denied = AdmissionVerificationError("revoked")
    monkeypatch.setattr(session_phases, "require_active_for_run", lambda _sid: (_ for _ in ()).throw(denied))
    with patch.object(session_phases, "em") as emit, \
         patch.object(session_phases, "_phase_clone", new=AsyncMock()) as clone:
        with pytest.raises(AdmissionVerificationError, match="revoked"):
            await session_phases.run_build(session)
    emit.assert_not_called()
    clone.assert_not_called()


@pytest.mark.asyncio
async def test_resume_consumes_fresh_child_before_status_save_and_schedule(admitted):
    existing = session_model.BuildSession(
        id="abcdef123456",
        repo_url="https://github.com/unite-group/pi-dev-ops.git",
        workspace="/tmp/runtime-resume",
        status="interrupted",
        last_completed_phase="analyze",
    )
    session_model._sessions[existing.id] = existing
    order: list[str] = []
    original_consume = admitted["transport"].consume_child

    def consume(payload):
        order.append("consume")
        return original_consume(payload)

    admitted["transport"].consume_child = consume
    body = ResumeRequest(
        brief=admitted["brief"],
        scope=admitted["scope"],
        senior_harness_admission_ref="child-runtime",
        senior_harness_reservation=admitted["reservation"],
        senior_harness_admission_envelope=admitted["envelope"],
    )
    with patch("app.server.routes.sessions.persistence.save_session", side_effect=lambda _s: order.append("save")), \
         patch("app.server.routes.sessions.asyncio.create_task") as create_task:
        create_task.side_effect = lambda coro: (order.append("schedule"), coro.close())[-1]
        result = await resume_session(existing.id, body)

    assert result == {"session_id": existing.id, "resumed_from": "analyze"}
    assert existing.status == "building"
    assert existing.scope == admitted["scope"]
    assert order == ["consume", "save", "schedule"]


@pytest.mark.asyncio
async def test_enforce_establishes_or_verifies_the_signed_base(admitted):
    session = session_model.BuildSession(
        id="abcdef123456",
        workspace="/tmp/admitted",
        senior_harness_reservation=admitted["reservation"],
    )
    run = AsyncMock(side_effect=[
        (0, "f" * 40 + "\n", ""),
        (0, "", ""),
        (0, "", ""),
        (0, "a" * 40 + "\n", ""),
    ])
    with patch.object(session_phases, "run_cmd", new=run):
        assert await session_phases._ensure_enforced_base(session, allow_checkout=True)
    assert run.await_count == 4

    with patch.object(
        session_phases,
        "run_cmd",
        new=AsyncMock(return_value=(0, "f" * 40 + "\n", "")),
    ), patch.object(session_phases, "_fail_phase") as fail:
        assert not await session_phases._ensure_enforced_base(
            session, allow_checkout=False
        )
    fail.assert_called_once()
