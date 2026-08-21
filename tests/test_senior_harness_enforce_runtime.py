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
from fastapi import HTTPException

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
         patch("app.server.routes.sessions.asyncio.create_task") as create_task, \
         patch(
             "app.server.session_phases.verify_workspace_identity",
             new=AsyncMock(side_effect=lambda *_args: order.append("preflight") or True),
         ):
        create_task.side_effect = lambda coro: (order.append("schedule"), coro.close())[-1]
        result = await resume_session(existing.id, body)

    assert result == {"session_id": existing.id, "resumed_from": "analyze"}
    assert existing.status == "building"
    assert existing.scope == admitted["scope"]
    assert order == ["preflight", "consume", "save", "schedule"]


@pytest.mark.asyncio
async def test_resume_rejects_workspace_drift_before_consumption_or_side_effect(admitted):
    existing = session_model.BuildSession(
        id="abcdef123456",
        repo_url="https://github.com/unite-group/pi-dev-ops.git",
        workspace="/tmp/runtime-resume",
        status="interrupted",
        last_completed_phase="analyze",
    )
    session_model._sessions[existing.id] = existing
    body = ResumeRequest(
        brief=admitted["brief"],
        scope=admitted["scope"],
        senior_harness_admission_ref="child-runtime",
        senior_harness_reservation=admitted["reservation"],
        senior_harness_admission_envelope=admitted["envelope"],
    )

    with patch(
        "app.server.session_phases.verify_workspace_identity",
        new=AsyncMock(return_value=False),
    ), patch("app.server.routes.sessions.persistence.save_session") as save, patch(
        "app.server.routes.sessions.asyncio.create_task"
    ) as create_task:
        with pytest.raises(HTTPException, match="does not match") as exc:
            await resume_session(existing.id, body)

    assert exc.value.status_code == 503
    assert admitted["transport"].consume_calls == []
    save.assert_not_called()
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_resume_workspace_identity_rejects_wrong_origin(admitted, tmp_path):
    run = AsyncMock(
        side_effect=[
            (0, "a" * 40 + "\n", ""),
            (0, "https://github.com/other-owner/other-repo.git\n", ""),
            (0, "https://github.com/unite-group/pi-dev-ops.git\n", ""),
        ]
    )
    with patch.object(session_phases, "run_cmd", new=run):
        assert not await session_phases.verify_workspace_identity(
            str(tmp_path),
            "a" * 40,
            "https://github.com/unite-group/pi-dev-ops.git",
        )


@pytest.mark.asyncio
async def test_workspace_identity_rejects_distinct_push_destination(
    admitted, tmp_path,
):
    expected_repo = "https://github.com/unite-group/pi-dev-ops.git"
    run = AsyncMock(
        side_effect=[
            (0, "a" * 40 + "\n", ""),
            (0, expected_repo + "\n", ""),
            (0, "https://github.com/other-owner/other-repo.git\n", ""),
        ]
    )
    with patch.object(session_phases, "run_cmd", new=run):
        assert not await session_phases.verify_workspace_identity(
            str(tmp_path),
            "a" * 40,
            expected_repo,
        )

    valid = AsyncMock(
        side_effect=[
            (0, "a" * 40 + "\n", ""),
            (0, expected_repo + "\n", ""),
            (0, expected_repo + "\n", ""),
        ]
    )
    with patch.object(session_phases, "run_cmd", new=valid):
        assert await session_phases.verify_workspace_identity(
            str(tmp_path),
            "a" * 40,
            expected_repo,
        )


@pytest.mark.asyncio
async def test_push_rechecks_complete_workspace_identity_before_git_side_effect(
    admitted, tmp_path,
):
    session = session_model.BuildSession(
        id="abcdef123456",
        repo_url="https://github.com/unite-group/pi-dev-ops.git",
        workspace=str(tmp_path),
        senior_harness_reservation=admitted["reservation"],
    )
    with patch.object(
        session_phases,
        "verify_workspace_identity",
        new=AsyncMock(return_value=False),
    ) as verify, patch.object(
        session_phases, "run_cmd", new=AsyncMock()
    ) as run, patch.object(session_phases, "_fail_phase") as fail:
        files, pushed = await session_phases._phase_push(session, 7)

    assert files == []
    assert pushed is False
    verify.assert_awaited_once_with(
        session.workspace,
        admitted["reservation"]["base_sha"],
        session.repo_url,
        allow_descendant=True,
    )
    run.assert_not_awaited()
    fail.assert_called_once()


@pytest.mark.asyncio
async def test_workspace_identity_checks_every_push_url_and_allows_base_descendant(
    admitted, tmp_path,
):
    expected_repo = "https://github.com/unite-group/pi-dev-ops.git"
    other_repo = "https://github.com/other-owner/other-repo.git"
    multiple_push = AsyncMock(
        side_effect=[
            (0, "a" * 40 + "\n", ""),
            (0, expected_repo + "\n", ""),
            (0, expected_repo + "\n" + other_repo + "\n", ""),
        ]
    )
    with patch.object(session_phases, "run_cmd", new=multiple_push):
        assert not await session_phases.verify_workspace_identity(
            str(tmp_path),
            "a" * 40,
            expected_repo,
        )

    descendant = AsyncMock(
        side_effect=[
            (0, "b" * 40 + "\n", ""),
            (0, "", ""),
            (0, expected_repo + "\n", ""),
            (0, expected_repo + "\n", ""),
        ]
    )
    with patch.object(session_phases, "run_cmd", new=descendant):
        assert await session_phases.verify_workspace_identity(
            str(tmp_path),
            "a" * 40,
            expected_repo,
            allow_descendant=True,
        )


@pytest.mark.asyncio
async def test_plan_discovery_authority_denial_escapes_before_workspace_write(
    admitted, tmp_path, monkeypatch,
):
    session = session_model.BuildSession(
        id="abcdef123456",
        repo_url="https://github.com/unite-group/pi-dev-ops.git",
        workspace=str(tmp_path),
        plan_discovery=True,
    )
    denied = AdmissionVerificationError("revoked during discovery")
    assertions = iter([None, denied])

    def assert_active(_sid):
        result = next(assertions)
        if isinstance(result, Exception):
            raise result

    monkeypatch.setattr(session_phases, "require_active_for_run", assert_active)
    with patch.object(
        session_phases, "_phase_clone", new=AsyncMock(return_value=True)
    ), patch.object(session_phases, "_phase_analyze"), patch.object(
        session_phases, "_phase_claude_check", new=AsyncMock(return_value=True)
    ), patch.object(
        session_phases, "_phase_sandbox", new=AsyncMock(return_value=True)
    ), patch.object(
        session_phases, "retrieve_similar_episodes", new=AsyncMock(return_value=[])
    ), patch(
        "app.server.agents.plan_discovery.discover_best_plan",
        new=AsyncMock(),
    ) as discover, patch.object(
        session_phases, "_write_task_memory", new=AsyncMock()
    ) as write_memory:
        with pytest.raises(AdmissionVerificationError, match="revoked"):
            await session_phases.run_build(session, brief=admitted["brief"])

    discover.assert_not_awaited()
    write_memory.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_shared_worktree_and_sandbox_paths_cannot_bypass_signed_base(
    admitted, tmp_path,
):
    shared = tmp_path / "shared" / "parent"
    shared.mkdir(parents=True)
    session = session_model.BuildSession(
        id="abcdef123456",
        repo_url="https://github.com/unite-group/pi-dev-ops.git",
        shared_workspace=str(shared),
        parent_session_id="parent-runtime",
        senior_harness_reservation=admitted["reservation"],
    )
    completed = type("Completed", (), {"returncode": 0, "stderr": ""})()
    with patch.object(
        session_phases.subprocess,
        "run",
        return_value=completed,
    ), patch.object(
        session_phases,
        "_ensure_enforced_base",
        new=AsyncMock(return_value=False),
    ) as ensure:
        assert not await session_phases._phase_clone(session, "")
    ensure.assert_awaited_once_with(session, allow_checkout=True)

    session.workspace = str(tmp_path)
    with patch.object(
        session_phases,
        "_ensure_enforced_base",
        new=AsyncMock(return_value=False),
    ) as ensure:
        assert not await session_phases._phase_sandbox(session, "sandbox")
    ensure.assert_awaited_once_with(session, allow_checkout=False)


def test_plan_discovery_asserts_active_immediately_before_model_call():
    tree = ast.parse(inspect.getsource(session_phases.run_build))
    function = tree.body[0]
    discovery_await = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "discover_best_plan"
    )
    discovery_statement = next(
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.Assign, ast.Expr))
        and node.lineno == discovery_await.lineno
    )
    guarding_try = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Try) and discovery_statement in node.body
    )
    index = guarding_try.body.index(discovery_statement)
    guard = guarding_try.body[index - 1]
    assert isinstance(guard, ast.Expr)
    assert isinstance(guard.value, ast.Call)
    assert isinstance(guard.value.func, ast.Name)
    assert guard.value.func.id == "require_active_for_run"
