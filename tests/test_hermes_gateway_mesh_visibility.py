"""Mission Control sees the Mac's Hermes gateway through the mesh heartbeat.

Production runs on Railway, where .harness/hermes/heartbeat.jsonl never exists,
so the hermes_gateway component could never be observed there. The Mac's mesh
heartbeat now reports the gateway process and health_full reads that row.
"""
import asyncio
import datetime
import time

import pytest

from app.server import supabase_log
from app.server.routes import health_full
from app.server.routes.health_aggregate import classify, run_with_timeout
from tests.mesh_helpers import load_module

_GATEWAY = (" 3306 /Volumes/Storage Unit/Application-Data/Hermes/hermes-agent/venv/bin/python"
            " -m hermes_cli.main gateway run --replace --external-supervisor")
_WATCHER = (" 10688 /Volumes/Storage Unit/Application-Data/Hermes/hermes-agent/venv/bin/python"
            " /Volumes/Storage Unit/Application-Data/Hermes/hermes-agent/tools/mcp_stdio_watch.py")


@pytest.fixture
def heartbeat(monkeypatch, tmp_path):
    mod = load_module("mesh_heartbeat_hermes", "mesh/heartbeat.py")
    monkeypatch.setattr(mod, "MESH_RUNNER_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    return mod


def _runtimes(mod, monkeypatch, ps: str) -> list[str]:
    monkeypatch.setattr(mod, "_run", lambda cmd, **kw: ps)
    return [a["runtime"] for a in mod.running_agent_sessions()]


def test_gateway_process_reported_as_its_own_runtime(heartbeat, monkeypatch):
    assert "hermes-gateway" in _runtimes(heartbeat, monkeypatch, _WATCHER + "\n" + _GATEWAY)


@pytest.mark.parametrize("ps", [
    " 812 /usr/bin/grep hermes_cli.main gateway run",
    " 813 /usr/bin/grep -m hermes_cli.main gateway run",
    """ 814 /usr/bin/python3 -c print("hermes_cli.main gateway run")""",
    " 815 /bin/echo /venv/bin/python -m hermes_cli.main gateway run",
    " 816 /venv/bin/python -m hermes_cli.main gateway runner",
    " 817 /venv/bin/python -m hermes_cli.main gateway status",
])
def test_text_mentioning_the_gateway_is_not_the_gateway(heartbeat, monkeypatch, ps):
    assert "hermes-gateway" not in _runtimes(heartbeat, monkeypatch, ps)


def test_other_hermes_processes_are_not_the_gateway(heartbeat, monkeypatch):
    runtimes = _runtimes(heartbeat, monkeypatch, _WATCHER)
    assert "hermes" in runtimes
    assert "hermes-gateway" not in runtimes


def _mesh(monkeypatch, tmp_path, status, rows):
    monkeypatch.setattr(health_full, "_HARNESS", tmp_path)  # no local heartbeat file
    monkeypatch.setattr(supabase_log, "_request", lambda *a, **k: (status, rows))
    return asyncio.run(health_full._check_hermes_gateway())


def _ago(seconds: int) -> str:
    now = datetime.datetime.now(datetime.UTC)
    return (now - datetime.timedelta(seconds=seconds)).isoformat()


def test_fresh_mesh_row_is_live(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200,
              [{"machine": "Phills-Mac-mini.local", "state": "working", "updated_at": _ago(30)}])
    assert (r["ok"], r["observed"], r["status"]) == (True, True, "live")
    assert r["machine"] == "Phills-Mac-mini.local"


def test_old_mesh_row_is_stale_and_red(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": _ago(3600)}])
    assert (r["ok"], r["observed"], r["status"]) == (False, True, "stale")


def test_gateway_gone_while_mac_alive_is_down(monkeypatch, tmp_path):
    """Heartbeat still beating, gateway process gone: the server marks the row idle."""
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "idle", "updated_at": _ago(30)}])
    assert (r["ok"], r["observed"], r["status"]) == (False, True, "down")


def test_postgrest_timestamp_format_parses(monkeypatch, tmp_path):
    ts = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=5)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f+00:00")
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": ts}])
    assert r["status"] == "live"


def test_no_row_is_not_observed(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200, [])
    assert (r["ok"], r["observed"], r["status"]) == (False, False, "not_observed")
    assert "error" not in r


def test_failed_read_is_not_an_empty_fleet(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 0, None)
    assert (r["ok"], r["observed"]) == (False, False)
    assert "read failed" in r["error"]


def test_slow_mesh_read_degrades_instead_of_reddening(monkeypatch, tmp_path):
    """Reviewer P1: a read slower than the 2 s aggregator deadline was cancelled
    into a red 'timeout'. It must surface as not observed (degraded)."""
    monkeypatch.setattr(health_full, "_HARNESS", tmp_path)
    monkeypatch.setattr(supabase_log, "_request", lambda *a, **k: time.sleep(2.1) or (0, None))
    name, payload = asyncio.run(run_with_timeout("hermes_gateway", health_full._check_hermes_gateway))
    verdict = classify({name: payload})
    assert verdict["red_components"] == []
    assert verdict["degraded_components"] == ["hermes_gateway"]


def test_malformed_row_is_not_observed(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": "garbage"}])
    assert (r["ok"], r["observed"]) == (False, False)
