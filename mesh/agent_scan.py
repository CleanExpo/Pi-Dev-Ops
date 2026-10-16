"""Which agent runtimes are running, from `ps -axo pid=,command=` output.

Split out of heartbeat.py (300-line ceiling); heartbeat.py is the only caller.
"""
from __future__ import annotations

import re

# The gateway is a Python interpreter running `-m hermes_cli.main gateway run`.
# Anchored on the executable so a grep, an echo or `python -c "..."` that merely
# mentions the command cannot fabricate a live gateway. The executable path may
# contain spaces ("/Volumes/Storage Unit/..."), but a continuation word never
# starts with "/" or "-", which is where an argument to another program would.
_HERMES_GATEWAY = re.compile(
    r"^\s*\d+\s+\S*?(?: [^\s/-]\S*?)*?/python[\d.]*\s+-m\s+hermes_cli\.main\s+gateway\s+run(?:\s|$)")


def scan_agent_processes(ps: str) -> list[dict]:
    """Match agent runtime binaries in `ps -axo pid=,command=` output."""
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
        if _HERMES_GATEWAY.match(line):
            sessions.append({"runtime": "hermes-gateway", "state": "working"})
    return sessions
