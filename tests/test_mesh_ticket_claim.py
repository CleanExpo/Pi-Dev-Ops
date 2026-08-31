"""
test_mesh_ticket_claim.py — the autonomy poller claims through mesh_work_claims.

Two replicas polling Linear both saw the same Ready ticket and each started a
session on it: Linear's own state is not a lock, because the poll and the
transition are two round trips with a window in between. Rather than invent a
second lock, the poller takes the same `mesh_work_claims` row the mesh
dispatcher and a runner's `claim/self` contend on, guarded by the
`mesh_work_claims_one_open` partial unique index.

Companion to tests/test_session_lease.py, which owns the session-lease race.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def configured(monkeypatch):
    """Make `_cfg()` report a configured Supabase so the claim path runs."""
    from app.server import supabase_log

    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x.supabase.co", "svc-key"))

# ── Linear ticket claim reuses mesh_work_claims ───────────────────────────────


def test_linear_claim_inserts_into_mesh_work_claims(configured, monkeypatch):
    from app.server import session_lease, supabase_log

    calls = []
    monkeypatch.setattr(supabase_log, "_upsert", lambda t, r: calls.append(("upsert", t, r)) or True)
    monkeypatch.setattr(supabase_log, "_insert", lambda t, r: calls.append(("insert", t, r)) or True)

    assert session_lease.claim_linear_ticket("RA-99") is True
    kinds = [(c[0], c[1]) for c in calls]
    assert ("insert", "mesh_work_claims") in kinds
    # The FK mesh_work_claims.machine -> mesh_machines.host makes this mandatory:
    # PostgREST reports a violated FK as 409, indistinguishable from "claimed".
    assert kinds.index(("upsert", "mesh_machines")) < kinds.index(("insert", "mesh_work_claims"))
    row = [c[2] for c in calls if c[0] == "insert"][0]
    assert row["linear_id"] == "RA-99"
    assert row["state"] == "claimed"
    assert row["machine"] == session_lease.claim_machine()


def test_linear_claim_lost_on_conflict(configured, monkeypatch):
    """A 409 from mesh_work_claims_one_open means another worker owns it."""
    from app.server import session_lease, supabase_log

    monkeypatch.setattr(supabase_log, "_upsert", lambda t, r: True)
    monkeypatch.setattr(supabase_log, "_insert", lambda t, r: False)

    assert session_lease.claim_linear_ticket("RA-99") is False


def test_transition_skips_a_ticket_owned_by_another_worker(monkeypatch):
    """Autonomy must not transition a ticket it lost the claim on."""
    from app.server import autonomy

    monkeypatch.setattr(autonomy.session_lease, "claim_linear_ticket", lambda _id: False)
    called = []
    monkeypatch.setattr(autonomy, "transition_issue", lambda *a, **k: called.append(a))

    out = autonomy._transition_to_in_progress(
        SimpleNamespace(LINEAR_API_KEY="k"), "iid", "RA-99", "t", "team",
    )
    assert out is None
    assert called == [], "a lost claim must not touch Linear"


def test_transition_proceeds_when_the_claim_is_won(monkeypatch):
    from app.server import autonomy

    monkeypatch.setattr(autonomy.session_lease, "claim_linear_ticket", lambda _id: True)
    monkeypatch.setattr(autonomy, "transition_issue", lambda *a, **k: None)

    out = autonomy._transition_to_in_progress(
        SimpleNamespace(LINEAR_API_KEY="k"), "iid", "RA-99", "t", "team",
    )
    assert out == "Pi-Dev: In Progress"


def test_claim_machine_collapses_cloud_replicas(monkeypatch):
    """mesh_machines.host is a PK the heartbeat owns — a per-deploy container id
    would leave a dead row behind on every Railway redeploy."""
    from app.server import session_lease

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert session_lease.claim_machine() == "railway"
    monkeypatch.delenv("RAILWAY_ENVIRONMENT")
    assert session_lease.claim_machine() == session_lease.local_host()
