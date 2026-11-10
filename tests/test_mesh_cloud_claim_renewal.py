"""tests/test_mesh_cloud_claim_renewal.py - M-PDO-REAPER-CLOUD-CLAIM-TTL.

The shared `railway` cloud claim never heartbeats, so the reaper released a cloud
claim at the TTL even while its session ran. The session now renews its own claim
(claimed_at); a dead replica stops renewing and is still reaped. Tests drive the
public lifecycle against one stateful mesh_work_claims table that honours the
PostgREST filters the code sends, so they do not depend on how the renewer is built.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

TTL_MIN = 90


def _ago(minutes: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


class FakeClaims:
    """mesh_work_claims + mesh_fleet, speaking both client dialects.

    `request` is `supabase_log._request` (returns parsed rows); `sb` / `get` are
    the reaper's collaborators (return a JSON string body).
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.fleet_stale: dict[str, bool] = {}
        self.renewals = 0
        self.fail_renewals: str | None = None  # "500" | "raise"
        self.before_release: Callable[[str], None] | None = None  # callable(path) run just before a reaper PATCH

    @staticmethod
    def _filters(path: str) -> dict[str, str]:
        query = path.split("?", 1)[1] if "?" in path else ""
        return dict(urllib.parse.parse_qsl(query, keep_blank_values=True))

    def _match(self, row: dict, f: dict[str, str]) -> bool:
        for col, spec in f.items():
            if col in ("select", "order"):
                continue
            op, _, val = spec.partition(".")
            if col == "state" and op == "in":
                if row["state"] not in val.strip("()").split(","):
                    return False
            elif op == "eq":
                if str(row.get(col)) != val:
                    return False
            elif col == "claimed_at" and op in ("lt", "lte"):
                bound = datetime.fromisoformat(val)
                if not (row["claimed_at"] < bound if op == "lt" else row["claimed_at"] <= bound):
                    return False
            else:
                raise AssertionError(f"fake does not understand filter {col}={spec}")
        return True

    def _patch(self, path: str, body: dict) -> list[dict]:
        f = self._filters(path)
        hit = [r for r in self.rows.values() if self._match(r, f)]
        for r in hit:
            if "claimed_at" in body:
                self.renewals += 1
                r["claimed_at"] = datetime.fromisoformat(body["claimed_at"])
            if "state" in body:
                r["state"] = body["state"]
        return hit

    def request(self, method: str, path: str, body: dict | None = None,
                prefer: str = "return=minimal") -> tuple[int, list[dict] | None]:
        table = path.split("?", 1)[0]
        if table == "mesh_machines":
            return 201, None
        if method == "POST" and table == "mesh_work_claims":
            if any(r["linear_id"] == body["linear_id"] and r["state"] in ("claimed", "working")
                   for r in self.rows.values()):
                return 409, None
            self.rows[body["id"]] = {**body, "claimed_at": datetime.now(timezone.utc)}
            return 201, None
        if method == "PATCH" and table == "mesh_work_claims":
            if body and "claimed_at" in body and self.fail_renewals:
                if self.fail_renewals == "raise":
                    raise RuntimeError("network partition")
                return 500, None
            hit = self._patch(path, body)
            return 200, [dict(r, claimed_at=r["claimed_at"].isoformat()) for r in hit]
        raise AssertionError(f"unexpected request {method} {path}")

    def sb(self, method: str, path: str, body: dict | None = None, *, prefer: str = "") -> tuple[int, str]:
        if method == "GET":
            return self.get(path)
        if self.before_release:
            self.before_release(path)
        status, rows = self.request(method, path, body)
        return status, json.dumps(rows or [])

    def get(self, path: str) -> tuple[int, str]:
        if path.startswith("mesh_fleet"):
            return 200, json.dumps([{"host": h, "is_stale": s} for h, s in self.fleet_stale.items()])
        f = self._filters(path)
        hit = [{k: (v.isoformat() if k == "claimed_at" else v) for k, v in r.items()}
               for r in self.rows.values() if self._match(r, f)]
        return 200, json.dumps(hit)

    def age(self, minutes: float) -> None:
        for r in self.rows.values():
            r["claimed_at"] = _ago(minutes)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeClaims]:
    from app.server import session_lease, supabase_log

    fake = FakeClaims()
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x.supabase.co", "svc-key"))
    monkeypatch.setattr(supabase_log, "_request", fake.request)
    monkeypatch.setattr(session_lease, "_OWN_CLAIMS", {})
    for var in ("RAILWAY_ENVIRONMENT", "RENDER", "FLY_APP_NAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MESH_CLAIM_RENEW_INTERVAL_S", "0.02")
    monkeypatch.setenv("MESH_CLAIM_RENEW_MAX_MINUTES", "60")
    yield fake
    for ident in list(session_lease._OWN_CLAIMS):  # never leave a renewer running
        session_lease.release_linear_ticket(ident, "released")


def _reap(fake: FakeClaims) -> list[dict]:
    from app.server import mesh_reaper

    return mesh_reaper.reap(fake.get, fake.sb, lambda _lid: None, TTL_MIN)


def _renewers() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("claim-renew") and t.is_alive()]


def _wait(cond: Callable[[], Any], timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def _claim(ident: str = "UNI-1") -> None:
    from app.server import session_lease as lease

    assert lease.claim_linear_ticket(ident) is True


def _only_row(fake: FakeClaims) -> dict:
    return next(iter(fake.rows.values()))


def test_cloud_claim_still_renewed_by_its_session_is_not_reaped(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    _claim()
    world.age(TTL_MIN + 30)  # the session has now outlived the TTL
    assert _wait(lambda: _only_row(world)["claimed_at"] > _ago(5)), "session never renewed its claim"
    assert _reap(world) == []
    assert _only_row(world)["state"] == "claimed"


def test_reap_cannot_release_a_claim_renewed_after_it_was_read(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    """Candidate read, then the session renews, then the reaper PATCHes: the release
    itself must refuse a row that is no longer stale (no read-then-write gap)."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("MESH_CLAIM_RENEW_INTERVAL_S", "3600")  # renewals out of the picture
    _claim()
    world.age(TTL_MIN + 30)
    world.before_release = lambda _path: world.age(0)  # the session renews just now
    assert _reap(world) == []
    assert _only_row(world)["state"] == "claimed"


def test_cloud_claim_whose_renewals_stopped_is_reaped(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    _claim()
    world.fail_renewals = "500"  # replica cut off from Supabase: it can no longer renew
    world.age(TTL_MIN + 30)
    time.sleep(0.15)  # several renewal intervals pass; none can land
    assert [r["linear_id"] for r in _reap(world)] == ["UNI-1"]
    assert _only_row(world)["state"] == "released"


def test_renewal_stops_after_its_maximum_lifetime(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    """A claim kept after a terminal session must not be held forever."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("MESH_CLAIM_RENEW_MAX_MINUTES", "0.002")  # about 0.12 s
    _claim()
    assert _wait(lambda: not _renewers()), "renewer outlived its maximum lifetime"
    world.age(TTL_MIN + 30)
    assert [r["linear_id"] for r in _reap(world)] == ["UNI-1"]


def test_renewal_runs_while_claimed_and_stops_on_release(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.server import session_lease

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    _claim()
    assert _wait(lambda: len(_renewers()) == 1 and world.renewals >= 2), "no renewal while claimed"
    assert session_lease.release_linear_ticket("UNI-1", "done") is True
    assert _wait(lambda: not _renewers()), "renewer still alive after release"
    seen = world.renewals
    time.sleep(0.1)
    assert world.renewals == seen
    assert _only_row(world)["state"] == "done"


def test_renewal_stops_when_session_start_fails(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    """fail_start is the exception path of the autonomy poller."""
    from app.server import autonomy_queue as aq

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    _claim()
    assert _wait(lambda: len(_renewers()) == 1)
    monkeypatch.setattr(aq, "_park", lambda *a, **k: None)
    aq.fail_start("key", "issue-uuid", "UNI-1", "team", RuntimeError("boom"))
    assert _wait(lambda: not _renewers()), "renewer outlived a failed session start"
    assert _only_row(world)["state"] == "failed"


def test_renewal_stops_when_a_failed_session_keeps_its_claim(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed ticket that cannot be labelled keeps its claim (so nobody re-claims an
    unlabelled failure) - but the session is over, so it must stop being renewed."""
    from types import SimpleNamespace

    from app.server import autonomy_queue as aq

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    _claim()
    assert _wait(lambda: len(_renewers()) == 1)
    aq.remember_claim("issue-uuid", "UNI-1")
    monkeypatch.setattr(aq, "_autonomy", lambda: SimpleNamespace(
        _gql=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("linear down")),
        _TEAM_ID="t", add_label_to_issue=lambda *a, **k: False))
    session = SimpleNamespace(linear_issue_id="issue-uuid", status="failed", autonomy_triggered=True)
    try:
        aq.release_session_claim(session)
    finally:
        aq._CLAIMED.pop("issue-uuid", None)
    assert _only_row(world)["state"] == "claimed"  # claim kept on purpose
    assert _wait(lambda: not _renewers()), "renewer kept running for a finished session"


def test_renewal_failure_is_logged_and_never_crashes_the_session(
    world: FakeClaims, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    world.fail_renewals = "raise"
    with caplog.at_level(logging.WARNING):
        _claim()  # the claim itself must still succeed
        assert _wait(lambda: any("renew" in r.getMessage().lower() for r in caplog.records)), \
            "renewal failure was not logged"
        assert len(_renewers()) == 1, "renewer died on the first failure"
    world.fail_renewals = None  # outage over: it recovers on its own
    world.age(TTL_MIN + 30)
    assert _wait(lambda: _only_row(world)["claimed_at"] > _ago(5)), "renewer did not recover"


def test_renewal_never_resurrects_a_claim_the_reaper_released(world: FakeClaims, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    _claim()
    assert _wait(lambda: len(_renewers()) == 1)
    _only_row(world)["state"] = "released"
    assert _wait(lambda: not _renewers()), "renewer kept going after its claim was released"
    assert _only_row(world)["state"] == "released"


def test_non_cloud_claim_is_not_renewed(world: FakeClaims) -> None:
    _claim()
    time.sleep(0.1)
    assert not _renewers()
    assert world.renewals == 0


def test_non_cloud_claim_reaping_is_unchanged(world: FakeClaims) -> None:
    _claim()
    row = _only_row(world)
    row["machine"] = "nodeA"
    world.age(TTL_MIN + 30)
    world.fleet_stale = {"nodeA": False}  # fresh heartbeat: left alone
    assert _reap(world) == []
    world.fleet_stale = {"nodeA": True}  # dead machine: reaped
    assert [r["linear_id"] for r in _reap(world)] == ["UNI-1"]
