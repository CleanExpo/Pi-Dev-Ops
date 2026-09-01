"""tests/mesh_reap_helpers.py — shared fakes for the stale-claim reaper suites.

`test_mesh_claim_reap.py` (UNI-2301, the reaper's own behaviour) and
`test_mesh_read_safety.py` (RA-7405, what it does when a read fails) both need
the same in-memory Supabase and Linear. Extracted rather than duplicated, and
extracted rather than grown in place: `test_mesh_claim_reap.py` sits on a
510-line size-gate baseline of 403 and the repo's rule is to extract when you
touch a baselined file, never to raise its entry.

Same reasoning, and the same shape, as `tests/mesh_helpers.py`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

HDR = {"X-Pi-CEO-Secret": "test-secret"}

# A PostgREST error is VALID JSON returned with a non-2xx status — `_sb` returns
# it rather than raising, which is the half of RA-7405 that reached production.
PGRST_401 = json.dumps({"message": "JWT expired", "code": "PGRST301"})


def old(minutes):
    """A timestamp `minutes` in the past, for building past-TTL claims."""
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


class FakeSupabase:
    """Models mesh_work_claims + mesh_fleet for the reap sweep.

    claims: {linear_id: {"id", "machine", "state", "claimed_at"}}
    fleet_stale: {host: is_stale bool}
    """

    def __init__(self, claims=None, fleet_stale=None, race_lids=None,
                 fleet_status=200, fleet_body=None):
        self.claims = claims or {}
        self.fleet_stale = fleet_stale or {}
        # RA-7405: let a test make the liveness read FAIL while still returning
        # (a non-2xx from PostgREST returns normally, it does not raise).
        self.fleet_status = fleet_status
        self.fleet_body = fleet_body
        self.patched: list[str] = []  # linear_ids released
        # linear_ids whose reap PATCH must return 0 rows, simulating a racing
        # reap (or the runner itself) having already flipped that claim's state.
        self.race_lids = race_lids or set()

    def sb(self, method, path, body=None, *, prefer=""):
        if method == "GET" and path.startswith("mesh_work_claims?select=id,linear_id,machine,claimed_at"):
            cutoff_str = path.split("claimed_at=lt.")[1]
            import urllib.parse as _up
            cutoff = datetime.fromisoformat(_up.unquote(cutoff_str))
            rows = [
                {"id": lid, "linear_id": lid, "machine": c["machine"], "claimed_at": c["claimed_at"].isoformat()}
                for lid, c in self.claims.items()
                if c["state"] in ("claimed", "working") and c["claimed_at"] < cutoff
            ]
            return 200, json.dumps(rows)
        if method == "GET" and path == "mesh_fleet?select=host,is_stale":
            if self.fleet_status >= 300:
                return self.fleet_status, self.fleet_body or ""
            return 200, json.dumps([{"host": h, "is_stale": s} for h, s in self.fleet_stale.items()])
        if method == "PATCH" and path.startswith("mesh_work_claims?id=eq."):
            lid = path.split("id=eq.")[1].split("&")[0]
            if lid in self.race_lids:
                return 200, json.dumps([])  # raced: nothing actually updated
            if lid in self.claims and self.claims[lid]["state"] in ("claimed", "working"):
                self.claims[lid]["state"] = "released"
                self.patched.append(lid)
                return 200, json.dumps([{"id": lid, "state": "released"}])
            return 200, json.dumps([])
        if method == "PATCH" and path.startswith("mesh_work_claims?linear_id=eq."):
            # Mirrors return=representation like the real PostgREST: the row on
            # a match, [] when the state filter matched nothing (0-row race —
            # claim already done/absent), still with a 2xx status either way.
            lid = path.split("linear_id=eq.")[1].split("&")[0]
            if lid in self.claims and self.claims[lid]["state"] in ("claimed", "working"):
                self.claims[lid]["state"] = (body or {}).get("state", self.claims[lid]["state"])
                self.patched.append(lid)
                return 200, json.dumps([{"linear_id": lid, "state": self.claims[lid]["state"]}])
            return 200, json.dumps([])
        return 200, "[]"


class FakeLinear:
    """Models the issue(id) lookup + team states + issueUpdate mutation used
    to move a reaped issue back to an unstarted state."""

    def __init__(self, *, team_of=None):
        self.team_of = team_of or {}  # linear_id -> team_id
        self.moved_to_unstarted: set[str] = set()

    def graphql(self, query: str) -> dict:
        if query.startswith("query{issue(id:"):
            lid = query.split('id:"')[1].split('"')[0]
            team_id = self.team_of.get(lid)
            if not team_id:
                return {"issue": None}
            return {"issue": {"id": lid, "team": {"id": team_id}}}
        if query.startswith("query{team"):
            return {"team": {"states": {"nodes": [
                {"id": "st-todo", "type": "unstarted", "position": 0},
                {"id": "st-progress", "type": "started", "position": 1}]}}}
        if query.startswith("mutation{issueUpdate"):
            issue_id = query.split('id:"')[1].split('"')[0]
            state_id = query.split('stateId:"')[1].split('"')[0]
            if state_id == "st-todo":
                self.moved_to_unstarted.add(issue_id)
            return {"issueUpdate": {"success": True}}
        return {}
