"""Goal analysis worker, routes and off switch (UNI-3306 PR 2).

The store is the real goal_analysis_jobs module over the FakeRest database (its clock is
the database clock); only the model call and the project lookup are faked. Cases named
kill / stop / double are the Q9 acceptance: pytest -k "kill or stop or double".
Limits, loop-blocking and model-lifetime cases: test_goal_analysis_worker_limits.py.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server import goal_analysis_jobs as jobs, goal_analysis_worker as worker
from app.server.auth import require_auth, require_rate_limit
from app.server.routes import goal_ticket as goal_ticket_route
from app.server.routes import goal_ticket_async
from tests import goal_worker_helpers as h
from tests.goal_jobs_helpers import CLAIM, MARGIN, FakeRest
from tests.goal_worker_helpers import ACCEPT, GOAL, Model, _queued, _row

# fixtures are taken by assignment, not import (ruff F811)
_fresh_slots, rest, launched, async_on = h._fresh_slots, h.rest, h.launched, h.async_on


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(goal_ticket_route.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app)


BODY = {"goal": GOAL, "acceptance": ACCEPT, "project_id": "ra"}


# ---- the off switch ---------------------------------------------------------------------

def test_switch_off_post_runs_inline_exactly_as_today(
        client: TestClient, monkeypatch: pytest.MonkeyPatch, launched: list[str]) -> None:
    monkeypatch.delenv("GOAL_ANALYZE_ASYNC", raising=False)
    assert worker.enabled() is False  # the default
    seen: list[tuple[Any, ...]] = []

    async def inline(goal: str, acceptance: str, project_id: str) -> dict[str, Any]:
        seen.append((goal, acceptance, project_id))
        return {"status": "proposed", "filed": False, "tickets": []}

    monkeypatch.setattr(goal_ticket_route, "analyze_goal", inline)
    resp = client.post("/api/goal-ticket/analyze", json={**BODY, "idempotency_key": "ignored-key-1"})
    assert resp.status_code == 200 and resp.json()["status"] == "proposed"
    assert seen == [(GOAL, ACCEPT, "ra")] and launched == []
    assert client.get("/api/goal-ticket/analyze/anything").status_code == 404


def test_switch_on_post_returns_202_with_the_job(
        client: TestClient, rest: FakeRest, async_on: None, launched: list[str]) -> None:
    resp = client.post("/api/goal-ticket/analyze", json={**BODY, "idempotency_key": "key-0001"})
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "queued" and launched == [job["id"]]
    again = client.post("/api/goal-ticket/analyze", json={**BODY, "idempotency_key": "key-0001"})
    assert again.status_code == 202 and again.json()["id"] == job["id"]
    assert client.get(f"/api/goal-ticket/analyze/{job['id']}").json()["status"] == "queued"


def test_switch_on_but_table_missing_is_503_never_inline(
        client: TestClient, rest: FakeRest, monkeypatch: pytest.MonkeyPatch, launched: list[str]) -> None:
    monkeypatch.setenv("GOAL_ANALYZE_ASYNC", "1")
    rest.missing = True
    resp = client.post("/api/goal-ticket/analyze", json=BODY)
    assert resp.status_code == 503 and resp.json()["detail"]["error"] == "async_unavailable"
    assert launched == []


def test_status_read_failure_is_an_error_not_not_found(
        client: TestClient, rest: FakeRest, async_on: None) -> None:
    job_id = _queued()
    rest.missing = True
    resp = client.get(f"/api/goal-ticket/analyze/{job_id}")
    assert resp.status_code == 503 and resp.json()["detail"]["error"] == "table_missing"
    rest.missing = False
    assert client.get("/api/goal-ticket/analyze/00000000-0000-0000-0000-000000000009").status_code == 404


def test_status_route_uses_auth_only_no_rate_limit() -> None:
    route = next(r for r in goal_ticket_route.router.routes
                 if getattr(r, "path", "") == "/api/goal-ticket/analyze/{job_id}")
    deps = [d.call for d in route.dependant.dependencies]
    assert require_auth in deps and require_rate_limit not in deps


# ---- startup probe -----------------------------------------------------------------------

async def test_startup_probe_missing_table_leaves_async_unavailable(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOAL_ANALYZE_ASYNC", "1")
    rest.missing = True
    started: list[str] = []
    await worker.start(lambda factory, name: started.append(name))
    assert worker.availability()[0] is False and started == []
    rest.missing = False
    await worker.start(lambda factory, name: started.append(name) or asyncio.sleep(0))
    assert worker.availability()[0] is True


# ---- the worker --------------------------------------------------------------------------

async def test_run_job_finishes_with_tickets_and_no_fallback(rest: FakeRest) -> None:
    job_id, model = _queued(), Model()
    assert await worker.run_job(job_id, complete_fn=model, heartbeat_s=1000) == "finished"
    row = _row(rest, job_id)
    assert row["status"] == "finished" and row["result"]["fallback"] is False
    assert row["result"]["tickets"][0]["title"] == "Finish stage one"


async def test_model_without_a_plan_is_recorded_failed_with_reason(rest: FakeRest) -> None:
    job_id = _queued()
    assert await worker.run_job(job_id, complete_fn=Model("no json here"), heartbeat_s=1000) == "failed"
    row = _row(rest, job_id)
    assert row["status"] == "failed" and "usable ticket plan" in row["failure_reason"]
    assert row["result"] is None


async def test_double_submit_one_model_call(
        rest: FakeRest, async_on: None, launched: list[str]) -> None:
    first = await goal_ticket_async.submit_job(GOAL, ACCEPT, "ra", "key-0001")
    second = await goal_ticket_async.submit_job(GOAL, ACCEPT, "ra", "key-0001")
    third = await goal_ticket_async.submit_job(GOAL, ACCEPT, "ra", "another-key-2")  # same goal, new key
    assert first["id"] == second["id"] == third["id"] and len(rest.rows) == 1
    model = Model(hold=False)
    outcomes = await asyncio.gather(*(
        worker.run_job(job_id, complete_fn=model, heartbeat_s=1000) for job_id in launched + launched))
    assert model.calls == 1 and sorted(outcomes).count("finished") == 1
    assert outcomes.count("not_claimed") == len(outcomes) - 1


async def test_stop_reaches_the_model_within_5s_when_heartbeat_returns_false(rest: FakeRest) -> None:
    job_id, model = _queued(), Model(hold=True)
    task = asyncio.create_task(worker.run_job(job_id, complete_fn=model, heartbeat_s=0.05))
    await asyncio.sleep(0.02)
    rest.advance(CLAIM + 1)  # the claim lapses on the database clock: the next heartbeat is False
    started = time.monotonic()
    outcome = await asyncio.wait_for(task, 5)
    assert outcome == "abandoned" and model.stop_seen_at is not None
    assert model.stop_seen_at - started < 5
    assert _row(rest, job_id)["status"] == "running"  # the lost attempt wrote nothing, no retry


async def test_stop_after_lost_claim_never_writes_finish_or_fail(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = _queued()
    writes: list[str] = []
    for name in ("finish", "fail"):
        monkeypatch.setattr(jobs, name, lambda *a, _n=name: writes.append(_n) or True)
    task = asyncio.create_task(worker.run_job(job_id, complete_fn=Model(hold=True), heartbeat_s=0.05))
    await asyncio.sleep(0.02)
    rest.advance(CLAIM + 1)
    assert await asyncio.wait_for(task, 5) == "abandoned"
    assert writes == []


async def test_finish_refused_by_the_store_is_abandoned_not_retried(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(jobs, "finish", lambda *a: calls.append(1) or False)
    job_id = _queued()
    assert await worker.run_job(job_id, complete_fn=Model(), heartbeat_s=1000) == "abandoned"
    assert calls == [1]


async def _kill_mid_run(rest: FakeRest, job_id: str) -> None:
    """The server process dies mid-run: the task vanishes and nothing is written."""
    task = asyncio.create_task(worker.run_job(job_id, complete_fn=Model(forever=True), heartbeat_s=1000))
    await asyncio.sleep(0.02)
    assert _row(rest, job_id)["status"] == "running"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rest.advance(CLAIM + MARGIN + 1)


async def test_server_kill_mid_run_is_recovered_then_retried_once(
        rest: FakeRest, launched: list[str]) -> None:
    job_id = _queued()
    await _kill_mid_run(rest, job_id)
    assert _row(rest, job_id)["status"] == "running"  # a kill writes nothing
    await worker.recover_once()
    assert _row(rest, job_id)["status"] == "interrupted" and launched == [job_id]
    model = Model()
    assert await worker.run_job(job_id, complete_fn=model, heartbeat_s=1000) == "finished"
    row = _row(rest, job_id)
    assert row["status"] == "finished" and row["retry_count"] == 1 and row["attempt"] == 2


async def test_server_kill_twice_fails_the_job_after_its_one_retry(
        rest: FakeRest, launched: list[str]) -> None:
    job_id = _queued()
    await _kill_mid_run(rest, job_id)
    await worker.recover_once()
    await _kill_mid_run(rest, job_id)
    await worker.recover_once()
    row = _row(rest, job_id)
    assert row["status"] == "failed" and "one retry" in row["failure_reason"]
    assert launched == [job_id]  # never launched a third time


async def test_kill_before_claim_is_picked_up_by_recovery(rest: FakeRest, launched: list[str]) -> None:
    job_id = _queued()  # submitted, then the server died before it could claim
    await worker.recover_once()
    assert launched == [job_id]
