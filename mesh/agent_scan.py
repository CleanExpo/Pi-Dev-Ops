"""Which agent runtimes are running, from `ps -axo pid=,command=` output.

Split out of heartbeat.py (300-line ceiling); heartbeat.py is the only caller.
"""
from __future__ import annotations

import re

# The gateway is a Python interpreter whose argv is exactly
# `<python> -m hermes_cli.main gateway run ...`. Text matching alone cannot tell
# that apart from `echo venv/bin/python -m hermes_cli.main gateway run` (review
# P1, twice), so the executable comes from `ps -o comm=`, which on macOS is the
# real executable path, and the command line must start with exactly that path.
# On Linux `comm` is a bare name, so no gateway is reported there: the gateway
# runs only on the Mac mini, and a miss reads as "down" — loud, never false-live.
_PYTHON_EXE = re.compile(r"python[\d.]*")
_GATEWAY_ARGS = re.compile(r"-m\s+hermes_cli\.main\s+gateway\s+run(?:\s|$)")


def _exe_by_pid(comm: str) -> dict[str, str]:
    """`ps -axo pid=,comm=` output → {pid: executable path}."""
    exes = {}
    for line in comm.splitlines():
        pid, _, exe = line.strip().partition(" ")
        if pid.isdigit() and exe.strip():
            exes[pid] = exe.strip()
    return exes


def _is_hermes_gateway(line: str, exes: dict[str, str]) -> bool:
    pid, _, cmd = line.strip().partition(" ")
    exe, cmd = exes.get(pid, ""), cmd.strip()
    if not exe or not cmd.startswith(exe + " "):
        return False
    return bool(_PYTHON_EXE.fullmatch(exe.rsplit("/", 1)[-1])
                and _GATEWAY_ARGS.match(cmd[len(exe) + 1:]))


def scan_agent_processes(ps: str, comm: str = "") -> list[dict]:
    """Match agent runtimes in `ps -axo pid=,command=` output (`comm`: pid=,comm=)."""
    exes = _exe_by_pid(comm)
    sessions: list[dict] = []
    for line in ps.splitlines():
        low = line.lower()
        for rt in ("claude", "codex", "hermes"):
            # match the runtime binary, not arbitrary substrings
            if f"/{rt}" in low or low.split()[1:2] == [rt] if len(low.split()) > 1 else False:
                if rt == "claude" and "claude" not in low.split("/")[-1][:20]:
                    continue
                sessions.append({"runtime": rt, "state": "working"})
                break
        # The Telegram-facing Hermes gateway gets its own row: a bare "hermes"
        # match is any Hermes process (MCP watchers too), not the bot itself.
        # Mission Control's hermes_gateway health reads it (app/server/hermes_mesh_health.py).
        if _is_hermes_gateway(line, exes):
            sessions.append({"runtime": "hermes-gateway", "state": "working"})
    return sessions
