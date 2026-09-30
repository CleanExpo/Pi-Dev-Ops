"""Shared fixtures for the W1b claim-rule suites (test_w1b_claimable, test_w1b_mesh_go)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_PROJECT = "proj-alpha"
_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _ago(hours: float) -> str:
    return (_NOW - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _issue(ident="RA-1", *, state="Ready for Pi-Dev", labels=("pi-dev:autonomous",),
           project=_PROJECT, blockers=(), history=(), comments=()) -> dict:
    return {
        "id": f"uuid-{ident}", "identifier": ident, "title": f"t {ident}", "priority": 2,
        "state": {"name": state, "type": "unstarted"},
        "labels": {"nodes": [{"name": n} for n in labels]},
        "project": {"id": project},
        "inverseRelations": {"nodes": [
            {"type": "blocks", "issue": {"identifier": b, "state": {"type": t}}} for b, t in blockers]},
        "history": {"nodes": [{"createdAt": at, "toState": {"name": n}} for n, at in history]},
        "comments": {"nodes": [{"body": b, "createdAt": at} for b, at in comments]},
    }


_START = "🤖 **Pi-CEO autonomous session started**\n\n- Session ID: `x`"
