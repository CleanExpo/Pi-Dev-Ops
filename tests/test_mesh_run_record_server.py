"""tests/test_mesh_run_record_server.py — the server stores only values the runner can produce (UNI-2796).

Split from tests/test_mesh_run_record.py at the 300-line size gate. Review
round 10 found values the column cannot hold (NaN, Infinity) passing through
and failing the whole PATCH, and a 32-hex string accepted as a run id.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import mesh_run_record as srv  # noqa: E402


def _patch(**kw):
    return srv.record_patch(srv.RunRecordFields(**kw))


def test_a_duration_the_column_cannot_hold_is_dropped():
    for bad in (float("nan"), float("inf"), float("-inf"), -1.0, 1e12):
        assert "duration_s" not in _patch(duration_s=bad), bad
    assert _patch(duration_s=12.5) == {"duration_s": 12.5}


def test_an_exit_code_outside_what_a_process_returns_is_dropped():
    for bad in (-129, 256, 2**31, -(2**31)):
        assert "exit_code" not in _patch(exit_code=bad), bad
    for good in (-15, 0, 3, 255):
        assert _patch(exit_code=good) == {"exit_code": good}


def test_only_the_runners_exact_run_id_shape_is_stored():
    for bad in ("deadbeef" * 4, "deadbeef0", "deadbee", "DEADBEEF"):
        assert "run_id" not in _patch(run_id=bad), bad
    assert _patch(run_id="deadbeef") == {"run_id": "deadbeef"}


def test_a_claim_change_the_database_did_not_store_is_not_answered_ok(monkeypatch):
    """Round 16: claim_update returned {ok: True} over a 500 PATCH, so the row stayed `working`."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mesh_reap_helpers import HDR

    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    app = FastAPI()
    app.include_router(mesh.router)
    for status, expected in ((500, 502), (200, 200)):
        monkeypatch.setattr(mesh, "_sb", lambda *_a, status=status, **_k: (status, "[]"))
        r = TestClient(app).post("/api/mesh/claim/update", headers=HDR, json={
            "linear_id": "UNI-A", "state": "failed", "run_id": "0a1b2c3d", "error_code": "timeout"})
        assert r.status_code == expected, (status, r.status_code)


def test_a_nan_duration_never_reaches_the_database_payload():
    """The round-10 reproduction, end to end through patch_claim."""
    sent: list = []

    def sb(method, path, payload, prefer=""):
        sent.append(payload)
        return 200, "[]"

    srv.patch_claim(sb, "PATCH", "mesh_work_claims?linear_id=eq.X", {"state": "done"},
                    fields=srv.RunRecordFields(run_id="0a1b2c3d", duration_s=float("nan")))
    assert sent == [{"state": "done", "run_id": "0a1b2c3d"}]
