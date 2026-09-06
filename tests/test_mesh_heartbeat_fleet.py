import json
import time

import pytest

from tests.mesh_helpers import load_module


@pytest.fixture
def heartbeat(monkeypatch, tmp_path):
    mod = load_module("mesh_heartbeat_fleet", "mesh/heartbeat.py")
    monkeypatch.setattr(mod, "MESH_RUNNER_STATE", str(tmp_path / "state.json"))
    return mod, tmp_path


def test_windows_collect_is_online_without_process_inspection(heartbeat, monkeypatch):
    mod, _ = heartbeat
    calls = []
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod, "tailnet_ip", lambda: "100.64.0.3")
    monkeypatch.setattr(mod, "cpu_mem_load", lambda: (10.0, 20.0, None))
    monkeypatch.setattr(mod, "runtimes_present", lambda: [])
    monkeypatch.setattr(mod, "_run", lambda cmd, **kwargs: calls.append(cmd) or "")

    payload = mod.collect()

    assert calls == []
    assert payload["status"] == "online"
    assert payload["agents"] == []
    assert set(payload) == {
        "host", "os", "tailnet_ip", "status", "cpu_pct", "mem_pct",
        "load1", "agent_runtimes", "version", "agents",
    }


def test_windows_fresh_managed_breadcrumb_is_working(heartbeat, monkeypatch):
    mod, tmp_path = heartbeat
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    (tmp_path / "state.json").write_text(json.dumps({
        "runtime": "codex",
        "current_task": "UNI-2403",
        "session_id": "run-1",
        "state": "working",
        "ts": time.time(),
    }))

    agents = mod.running_agent_sessions()

    assert agents == [{
        "runtime": "codex", "current_task": "UNI-2403",
        "session_id": "run-1", "state": "working",
    }]


def test_windows_metrics_use_noninteractive_cim(heartbeat, monkeypatch):
    mod, _ = heartbeat
    calls = []
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod.os, "getloadavg", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        mod,
        "_run",
        lambda cmd, **kwargs: calls.append(cmd) or '{"cpu":25,"total":1000,"free":250}',
    )

    assert mod.cpu_mem_load() == (25.0, 75.0, None)
    assert calls[0][:3] == ["powershell", "-NoProfile", "-NonInteractive"]
    assert "Get-CimInstance" in calls[0][-1]


def test_windows_metrics_fail_closed_on_command_error(heartbeat, monkeypatch):
    mod, _ = heartbeat
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod.os, "getloadavg", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(mod, "_run", lambda *args, **kwargs: "")

    assert mod.cpu_mem_load() == (None, None, None)


def test_windows_metrics_preserve_valid_cpu_when_memory_is_bad(heartbeat, monkeypatch):
    mod, _ = heartbeat
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod.os, "getloadavg", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        mod, "_run", lambda *args, **kwargs: '{"cpu":25,"total":"bad","free":250}'
    )

    assert mod.cpu_mem_load() == (25.0, None, None)


def test_tailnet_ip_prefers_explicit_resolved_binary(heartbeat, monkeypatch):
    mod, _ = heartbeat
    calls = []
    monkeypatch.setenv("TAILSCALE_BIN", "/opt/tailscale/bin/tailscale")
    monkeypatch.setattr(mod, "_resolved_tailscale_candidates", lambda: ["/opt/tailscale/bin/tailscale"])
    monkeypatch.setattr(mod, "_run", lambda cmd, **kwargs: calls.append(cmd) or "100.64.0.2\n")

    assert mod.tailnet_ip() == "100.64.0.2"
    assert calls == [["/opt/tailscale/bin/tailscale", "ip", "-4"]]


def test_tailnet_ip_falls_through_invalid_candidate(heartbeat, monkeypatch):
    mod, _ = heartbeat
    calls = []
    monkeypatch.setattr(mod, "_resolved_tailscale_candidates", lambda: ["bad", "good"])
    monkeypatch.setattr(
        mod,
        "_run",
        lambda cmd, **kwargs: calls.append(cmd) or ("not-an-ip" if cmd[0] == "bad" else "100.64.0.4"),
    )

    assert mod.tailnet_ip() == "100.64.0.4"
    assert calls == [["bad", "ip", "-4"], ["good", "ip", "-4"]]


def test_tailnet_ip_selects_ipv4_from_mixed_output(heartbeat, monkeypatch):
    mod, _ = heartbeat
    monkeypatch.setattr(mod, "_resolved_tailscale_candidates", lambda: ["tailscale"])
    monkeypatch.setattr(mod, "_run", lambda *args, **kwargs: "warning\nfd7a:115c::1\n100.64.0.5")

    assert mod.tailnet_ip() == "100.64.0.5"


@pytest.mark.parametrize("output", ["", "not-an-ip", "999.1.1.1"])
def test_tailnet_ip_never_fabricates_invalid_ipv4(heartbeat, monkeypatch, output):
    mod, _ = heartbeat
    monkeypatch.setattr(mod, "_resolved_tailscale_candidates", lambda: ["tailscale"])
    monkeypatch.setattr(mod, "_run", lambda *args, **kwargs: output)

    assert mod.tailnet_ip() == ""
