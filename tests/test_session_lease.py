"""
test_session_lease.py — one machine per interrupted session.

The defect: three machines booting all called `fetch_interrupted_sessions()`,
got the same rows back, and each resumed every one of them. `sessions` had no
ownership column at all, unlike `mesh_work_claims` and its partial unique index.

The load-bearing test here is `test_two_claimants_exactly_one_wins`, which runs
both claimants against a fake PostgREST that models the actual concurrency
guard: the conditional PATCH matches rows by filter, and the loser's filter no
longer matches once the winner has written `claimed_by`. Nothing else in this
file proves the lock works — a claim that always returns True would pass every
other assertion.

All Supabase HTTP is faked at `supabase_log._request`, the single request path.
No live network. Checkpoint completeness is in tests/test_session_checkpoint_fields.py;
the Linear-ticket claim is in tests/test_mesh_ticket_claim.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest


# ── Fake PostgREST ────────────────────────────────────────────────────────────


class FakeSessionsTable:
    """A `sessions` table that honours the claim filter, including `or=(...)`.

    Models the one property the lease depends on: a conditional PATCH updates
    only the rows its filter still matches at the moment it runs. Postgres
    serialises the two statements; this serialises them by running them one
    after the other in the same thread, which is the same observable outcome.
    """

    def __init__(self, rows: list[dict]) -> None:
        self.rows = {r["id"]: dict(r) for r in rows}
        self.patch_calls: list[str] = []

    # -- filter matching ----------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _matches(self, row: dict, query: str) -> bool:
        sid = re.search(r"id=eq\.([^&]+)", query)
        if sid and row["id"] != sid.group(1):
            return False
        status = re.search(r"status=eq\.([^&]+)", query)
        if status and row.get("status") != status.group(1):
            return False
        or_clause = re.search(r"or=\(claimed_by\.is\.null,lease_expires_at\.lt\.([^)]+)\)", query)
        if or_clause:
            if row.get("claimed_by") is None:
                return True
            expiry = row.get("lease_expires_at")
            if not expiry:
                return False
            cutoff = datetime.fromisoformat(_unquote(or_clause.group(1)))
            return datetime.fromisoformat(expiry) < cutoff
        return True

    # -- the _request stand-in ----------------------------------------------

    def request(self, method: str, path: str, body=None, prefer: str = "return=minimal"):
        if method != "PATCH":
            return 200, None
        self.patch_calls.append(path)
        hit = [r for r in self.rows.values() if self._matches(r, path)]
        for row in hit:
            row.update(body or {})
        return 200, ([dict(r) for r in hit] if "representation" in prefer else None)


class UnconditionalSessionsTable(FakeSessionsTable):
    """Sabotage control: a PATCH that ignores the ownership half of the filter.

    This is what the code did before the lease existed — every caller "wins".
    Used to prove `test_two_claimants_exactly_one_wins` can actually fail.
    """

    def _matches(self, row: dict, query: str) -> bool:
        sid = re.search(r"id=eq\.([^&]+)", query)
        return not sid or row["id"] == sid.group(1)


def _unquote(value: str) -> str:
    import urllib.parse

    return urllib.parse.unquote(value)


@pytest.fixture
def configured(monkeypatch):
    """Make `_cfg()` report a configured Supabase so the claim path runs."""
    from app.server import supabase_log

    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x.supabase.co", "svc-key"))


def _interrupted_row(sid: str = "s1") -> dict:
    return {"id": sid, "status": "interrupted", "claimed_by": None, "lease_expires_at": None}


# ── The race: exactly one claimant wins ───────────────────────────────────────


def test_two_claimants_exactly_one_wins(configured, monkeypatch):
    """Two machines, one interrupted session. One True, one False — SEEN, not assumed."""
    from app.server import session_lease, supabase_log

    table = FakeSessionsTable([_interrupted_row("s1")])
    monkeypatch.setattr(supabase_log, "_request", table.request)

    first = session_lease.claim_interrupted_session("s1", "machine-a")
    second = session_lease.claim_interrupted_session("s1", "machine-b")

    assert [first, second] == [True, False], (
        f"expected exactly one winner, got machine-a={first} machine-b={second}"
    )
    assert table.rows["s1"]["claimed_by"] == "machine-a"
    assert len(table.patch_calls) == 2, "the loser must still have attempted the PATCH"


def test_race_test_fails_without_atomicity(configured, monkeypatch):
    """Positive control for the test above.

    With an unconditional PATCH — the pre-lease behaviour — BOTH claimants win.
    If this assertion ever reads [True, True] as acceptable, the race test above
    is no longer proving anything.
    """
    from app.server import session_lease, supabase_log

    table = UnconditionalSessionsTable([_interrupted_row("s1")])
    monkeypatch.setattr(supabase_log, "_request", table.request)

    first = session_lease.claim_interrupted_session("s1", "machine-a")
    second = session_lease.claim_interrupted_session("s1", "machine-b")

    assert [first, second] == [True, True], (
        "sabotage control did not reproduce the double-claim; the race test's "
        "guarantee is therefore unverified"
    )


def test_expired_lease_is_reclaimable(configured, monkeypatch):
    """A machine that died mid-resume cannot release its lease; expiry must."""
    from app.server import session_lease, supabase_log

    stale = _interrupted_row("s1")
    stale["claimed_by"] = "dead-machine"
    stale["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    ).isoformat(timespec="seconds")
    table = FakeSessionsTable([stale])
    monkeypatch.setattr(supabase_log, "_request", table.request)

    assert session_lease.claim_interrupted_session("s1", "machine-b") is True
    assert table.rows["s1"]["claimed_by"] == "machine-b"


def test_live_lease_blocks_a_second_machine(configured, monkeypatch):
    from app.server import session_lease, supabase_log

    held = _interrupted_row("s1")
    held["claimed_by"] = "machine-a"
    held["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(minutes=9)
    ).isoformat(timespec="seconds")
    table = FakeSessionsTable([held])
    monkeypatch.setattr(supabase_log, "_request", table.request)

    assert session_lease.claim_interrupted_session("s1", "machine-b") is False
    assert table.rows["s1"]["claimed_by"] == "machine-a"


def test_non_interrupted_row_is_not_claimable(configured, monkeypatch):
    """A session someone already resumed to `building` is not up for grabs."""
    from app.server import session_lease, supabase_log

    row = _interrupted_row("s1")
    row["status"] = "building"
    table = FakeSessionsTable([row])
    monkeypatch.setattr(supabase_log, "_request", table.request)

    assert session_lease.claim_interrupted_session("s1", "machine-b") is False


def test_claim_filter_shape(configured, monkeypatch):
    """The PATCH must carry status + ownership predicates and ask for the rows back."""
    from app.server import session_lease, supabase_log

    seen = {}

    def fake_request(method, path, body=None, prefer="return=minimal"):
        seen.update(method=method, path=path, body=body, prefer=prefer)
        return 200, [{"id": "s1"}]

    monkeypatch.setattr(supabase_log, "_request", fake_request)
    assert session_lease.claim_interrupted_session("s1", "host-x", lease_minutes=5) is True

    assert seen["method"] == "PATCH"
    assert "id=eq.s1" in seen["path"]
    assert "status=eq.interrupted" in seen["path"]
    assert "or=(claimed_by.is.null,lease_expires_at.lt." in seen["path"]
    assert seen["prefer"] == "return=representation"
    assert seen["body"]["claimed_by"] == "host-x"
    assert seen["body"]["lease_expires_at"] > datetime.now(timezone.utc).isoformat(timespec="seconds")


def test_two_rows_returned_is_not_a_win(configured, monkeypatch):
    """Won means EXACTLY one row. A broadened filter is a bug, not a claim."""
    from app.server import session_lease, supabase_log

    monkeypatch.setattr(supabase_log, "_request", lambda *a, **k: (200, [{"id": "s1"}, {"id": "s2"}]))
    assert session_lease.claim_interrupted_session("s1", "host-x") is False


@pytest.mark.parametrize("sid,host", [("", "h"), ("s1", ""), ("", "")])
def test_claim_rejects_empty_arguments(sid, host):
    from app.server import session_lease

    assert session_lease.claim_interrupted_session(sid, host) is False


def test_claim_is_a_noop_when_supabase_unconfigured(monkeypatch):
    """No shared table means no contention — failing closed would only stall."""
    from app.server import session_lease, supabase_log

    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("", ""))
    called = []
    monkeypatch.setattr(supabase_log, "_request", lambda *a, **k: called.append(a) or (0, None))

    assert session_lease.claim_interrupted_session("s1", "host-x") is True
    assert called == [], "unconfigured claim must not issue an HTTP request"


def test_supabase_log_reexport_delegates(configured, monkeypatch):
    """`supabase_log.claim_interrupted_session` is the documented entry point."""
    from app.server import supabase_log

    table = FakeSessionsTable([_interrupted_row("s1")])
    monkeypatch.setattr(supabase_log, "_request", table.request)

    assert supabase_log.claim_interrupted_session("s1", "machine-a") is True
    assert supabase_log.claim_interrupted_session("s1", "machine-b") is False
