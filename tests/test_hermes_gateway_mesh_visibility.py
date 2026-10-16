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

_PY = "/Volumes/Storage Unit/Application-Data/Hermes/hermes-agent/venv/bin/python"
# (pid, real executable from `ps -o comm=`, command line from `ps -o command=`)
_GATEWAY = ("3306", _PY, f"{_PY} -m hermes_cli.main gateway run --replace --external-supervisor")
_WRAPPER = ("1052", _PY, f"{_PY} -m hermes_cli.stderr_timestamp --error-log /x/gateway.error.log -- "
            f"{_PY} -m hermes_cli.main gateway run --replace --external-supervisor")
_WATCHER = ("10688", _PY, f"{_PY} {_PY.rsplit('/venv', 1)[0]}/tools/mcp_stdio_watch.py")


@pytest.fixture
def heartbeat(monkeypatch, tmp_path):
    mod = load_module("mesh_heartbeat_hermes", "mesh/heartbeat.py")
    monkeypatch.setattr(mod, "MESH_RUNNER_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    return mod


def _runtimes(mod, monkeypatch, *procs: tuple[str, str, str]) -> list[str]:
    command = "\n".join(f" {pid} {cmd}" for pid, _, cmd in procs)
    comm = "\n".join(f" {pid} {exe}" for pid, exe, _ in procs)
    monkeypatch.setattr(mod, "_run", lambda cmd, **kw: comm if "pid=,comm=" in cmd else command)
    return [a["runtime"] for a in mod.running_agent_sessions()]


def test_gateway_process_reported_as_its_own_runtime(heartbeat, monkeypatch):
    runtimes = _runtimes(heartbeat, monkeypatch, _WRAPPER, _WATCHER, _GATEWAY)
    assert runtimes.count("hermes-gateway") == 1


@pytest.mark.parametrize("proc", [
    ("812", "/usr/bin/grep", "/usr/bin/grep hermes_cli.main gateway run"),
    ("813", "/usr/bin/grep", "/usr/bin/grep -m hermes_cli.main gateway run"),
    ("814", "/usr/bin/python3", """/usr/bin/python3 -c print("-m hermes_cli.main gateway run")"""),
    ("815", "/bin/echo", "/bin/echo venv/bin/python -m hermes_cli.main gateway run"),
    ("816", "/usr/bin/grep", "/usr/bin/grep venv/bin/python -m hermes_cli.main gateway run"),
    ("817", "/bin/echo", "/bin/echo /venv/bin/python -m hermes_cli.main gateway run"),
    ("818", _PY, f"{_PY} -m hermes_cli.main gateway runner"),
    ("819", _PY, f"{_PY} -m hermes_cli.main gateway status"),
    ("820", "/bin/zsh", f"/bin/zsh -c {_PY} -m hermes_cli.main gateway run"),
    ("821", "python3", f"{_PY} -m hermes_cli.main gateway run"),  # Linux: comm is a bare name
    _WRAPPER,  # the launchd wrapper names the command after "--" but is not the gateway
])
def test_text_mentioning_the_gateway_is_not_the_gateway(heartbeat, monkeypatch, proc):
    assert "hermes-gateway" not in _runtimes(heartbeat, monkeypatch, proc)


def test_gateway_without_a_known_executable_is_not_reported(heartbeat, monkeypatch):
    monkeypatch.setattr(heartbeat, "_run", lambda cmd, **kw: "" if "pid=,comm=" in cmd else f" 3306 {_GATEWAY[2]}")
    assert "hermes-gateway" not in [a["runtime"] for a in heartbeat.running_agent_sessions()]


def test_other_hermes_processes_are_not_the_gateway(heartbeat, monkeypatch):
    runtimes = _runtimes(heartbeat, monkeypatch, _WATCHER)
    assert "hermes" in runtimes
    assert "hermes-gateway" not in runtimes


def _mesh(monkeypatch, tmp_path, status, rows, machine_beat=None, machine_status=200):
    """Stub PostgREST: the gateway row read, then its machine's last_seen read."""
    monkeypatch.setattr(health_full, "_HARNESS", tmp_path)  # no local heartbeat file
    beat = [] if machine_beat is False else [{"last_seen": machine_beat or _ago(5)}]

    def request(method, path, *a, **k):
        if path.startswith("mesh_machines"):
            return (machine_status, beat if machine_status == 200 else None)
        return (status, rows)
    monkeypatch.setattr(supabase_log, "_request", request)
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
    """The whole Mac went quiet: machine and gateway are both old."""
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": _ago(3600)}],
              machine_beat=_ago(3600))
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


def test_working_row_left_behind_by_failed_reconciliation_is_down(monkeypatch, tmp_path):
    """Review P1: idle reconciliation failed, so a dead gateway's row still says
    working - but the Mac kept beating without reporting it."""
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": _ago(120)}],
              machine_beat=_ago(5))
    assert (r["ok"], r["observed"], r["status"]) == (False, True, "down")


def test_gateway_reported_in_the_latest_beat_is_live(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": _ago(20)}],
              machine_beat=_ago(20))
    assert r["status"] == "live"


def test_failed_machine_read_is_not_observed(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": _ago(5)}],
              machine_status=0)
    assert (r["ok"], r["observed"]) == (False, False) and "mesh_machines read failed" in r["error"]


def test_missing_machine_row_is_not_observed(monkeypatch, tmp_path):
    r = _mesh(monkeypatch, tmp_path, 200, [{"machine": "m", "state": "working", "updated_at": _ago(5)}],
              machine_beat=False)
    assert (r["ok"], r["observed"]) == (False, False) and "error" not in r


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


@pytest.fixture
def mesh_route(monkeypatch):
    import sys

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh


@pytest.mark.parametrize("failing", ["PATCH", "POST mesh_agents"])
def test_heartbeat_reports_failed_agent_reconciliation(mesh_route, failing):
    """Review P1: a failed idle PATCH or agent upsert was acknowledged ok=true."""
    client, mesh = mesh_route

    def sb(method, path, body=None, *, prefer=""):
        return (503, "") if f"{method} {path}".startswith(failing) else (201, "")
    mesh._sb = sb
    hb = {"host": "m", "agents": [{"runtime": "hermes-gateway"}]}
    assert client.post("/api/mesh/heartbeat", json=hb, headers={"X-Pi-CEO-Secret": "test-secret"}).status_code == 502


def test_heartbeat_ok_when_every_write_lands(mesh_route):
    client, mesh = mesh_route
    mesh._sb = lambda *a, **k: (204, "")
    r = client.post("/api/mesh/heartbeat", json={"host": "m", "agents": [{"runtime": "hermes-gateway"}]},
                    headers={"X-Pi-CEO-Secret": "test-secret"})
    assert r.status_code == 200 and r.json()["ok"] is True
