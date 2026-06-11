#!/usr/bin/env python3
"""Nexus Mesh heartbeat — each fleet node runs this to publish its live state.

Spec: docs/superpowers/specs/2026-06-11-nexus-mesh-design.md

Zero third-party deps (urllib only), cross-platform (macOS + Windows + Linux).
Collects {host, os, tailnet_ip, cpu, mem, load, agent runtimes, running agent
sessions} and POSTs to the Pi-CEO Railway endpoint, which writes Supabase with
the service-role key. Machines never hold the Supabase key — only PI_CEO_API_KEY.

Run once (cron/launchd/Task Scheduler) or as a loop daemon:
    python3 heartbeat.py            # one shot
    python3 heartbeat.py --loop     # every HEARTBEAT_INTERVAL seconds
    python3 heartbeat.py --print    # collect + print, no network (debug)
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

PI_CEO_API_URL = os.environ.get("PI_CEO_API_URL", "https://pi-dev-ops-production.up.railway.app")
PI_CEO_API_KEY = os.environ.get("PI_CEO_API_KEY", "")
INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "20"))
AGENT_RUNTIMES = ("claude", "codex", "cursor-agent", "pi", "hermes")


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def tailnet_ip() -> str:
    for ts in ("/Applications/Tailscale.app/Contents/MacOS/Tailscale", "tailscale"):
        out = _run([ts, "ip", "-4"])
        if out:
            return out.splitlines()[0].strip()
    return ""


def cpu_mem_load() -> tuple[float | None, float | None, float | None]:
    """Best-effort CPU%, mem%, 1-min load — no psutil dependency."""
    load1 = None
    try:
        load1 = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass
    cpu = mem = None
    sysname = platform.system()
    if sysname == "Darwin":
        # mem: pages free vs total
        vm = _run(["vm_stat"])
        try:
            pages = {}
            for line in vm.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    pages[k.strip()] = int(v.strip().rstrip("."))
            free = pages.get("Pages free", 0) + pages.get("Pages inactive", 0)
            total = sum(pages.get(k, 0) for k in (
                "Pages free", "Pages active", "Pages inactive", "Pages speculative", "Pages wired down"))
            if total:
                mem = round(100 * (1 - free / total), 1)
        except Exception:
            pass
        ncpu = _run(["sysctl", "-n", "hw.ncpu"])
        if load1 is not None and ncpu.isdigit():
            cpu = round(min(100.0, 100 * load1 / int(ncpu)), 1)  # load-derived proxy
    elif sysname == "Linux":
        try:
            with open("/proc/meminfo") as f:
                mi = {l.split(":")[0]: int(l.split()[1]) for l in f if ":" in l}
            if mi.get("MemTotal"):
                mem = round(100 * (1 - mi.get("MemAvailable", 0) / mi["MemTotal"]), 1)
        except Exception:
            pass
        ncpu = os.cpu_count() or 1
        if load1 is not None:
            cpu = round(min(100.0, 100 * load1 / ncpu), 1)
    elif sysname == "Windows":
        out = _run(["wmic", "cpu", "get", "loadpercentage", "/value"])
        for line in out.splitlines():
            if line.startswith("LoadPercentage="):
                try:
                    cpu = float(line.split("=")[1])
                except ValueError:
                    pass
        mtot = _run(["wmic", "OS", "get", "TotalVisibleMemorySize", "/value"])
        mfree = _run(["wmic", "OS", "get", "FreePhysicalMemory", "/value"])
        try:
            t = int(mtot.split("=")[1]); fr = int(mfree.split("=")[1])
            mem = round(100 * (1 - fr / t), 1)
        except Exception:
            pass
    return cpu, mem, load1


def runtimes_present() -> list[dict]:
    from shutil import which
    out = []
    for r in AGENT_RUNTIMES:
        path = which(r)
        out.append({"runtime": r, "present": bool(path)})
    return out


def running_agent_sessions() -> list[dict]:
    """Cheap proc scan for live agent processes → mesh_agents rows."""
    sysname = platform.system()
    sessions: list[dict] = []
    if sysname in ("Darwin", "Linux"):
        ps = _run(["ps", "-axo", "pid=,command="], timeout=6)
        for line in ps.splitlines():
            low = line.lower()
            for rt in ("claude", "codex", "hermes"):
                # match the runtime binary, not arbitrary substrings
                if f"/{rt}" in low or low.split()[1:2] == [rt] if len(low.split()) > 1 else False:
                    if rt == "claude" and "claude" not in low.split("/")[-1][:20]:
                        continue
                    sessions.append({"runtime": rt, "state": "working"})
                    break
    # de-dup by runtime, cap noise
    seen, uniq = set(), []
    for s in sessions:
        if s["runtime"] not in seen:
            seen.add(s["runtime"]); uniq.append(s)
    return uniq


def collect() -> dict:
    cpu, mem, load1 = cpu_mem_load()
    agents = running_agent_sessions()
    status = "working" if agents else "idle"
    return {
        "host": socket.gethostname().split(".")[0],
        "os": f"{platform.system()} {platform.release()}",
        "tailnet_ip": tailnet_ip(),
        "status": status,
        "cpu_pct": cpu,
        "mem_pct": mem,
        "load1": load1,
        "agent_runtimes": runtimes_present(),
        "version": "nexus-mesh/0.1",
        "agents": agents,
    }


def publish(payload: dict) -> tuple[bool, str]:
    url = f"{PI_CEO_API_URL.rstrip('/')}/api/mesh/heartbeat"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {PI_CEO_API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, f"{r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"
    except Exception as e:
        return False, str(e)


def main() -> int:
    args = set(sys.argv[1:])
    if "--print" in args:
        print(json.dumps(collect(), indent=2))
        return 0
    if "--loop" in args:
        while True:
            ok, msg = publish(collect())
            print(json.dumps({"published": ok, "detail": msg, "ts": int(time.time())}))
            time.sleep(INTERVAL)
    ok, msg = publish(collect())
    print(json.dumps({"published": ok, "detail": msg}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
