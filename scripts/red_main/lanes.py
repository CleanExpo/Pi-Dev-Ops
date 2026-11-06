"""Pick the least-busy machine and start one fix lane there (RA-8174).

A lane is the existing away-mode job shape: ~/agent-work/<name>/{brief.md,run.sh}
where run.sh is a copy of ~/agent-work/lib/run-template.sh (lane_guard, a 3-session
queue, a status file and a watchdog). Only hosts that already carry that template
are eligible, so the PC (no bash lane runner) is never picked.

RED_MAIN_HOSTS="mini=local,macbook=macbook" names each host and how to reach it
("local", or an ssh alias). Busy = running `claude -p` sessions; an unreachable
host or one without the template is not eligible.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess

PROBE = ('n=$(pgrep -f "claude -p" | wc -l | tr -d " "); '
         't=no; [ -x "$HOME/agent-work/lib/run-template.sh" ] && t=yes; echo "busy=$n template=$t"')
SSH = ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes"]


def hosts() -> list[tuple[str, str]]:
    raw = os.environ.get("RED_MAIN_HOSTS", "mini=local,macbook=macbook")
    out = []
    for item in (x.strip() for x in raw.split(",") if x.strip()):
        name, _, via = item.partition("=")
        out.append((name, via or name))
    return out


def run_on(via: str, script: str, timeout: float = 30) -> tuple[bool, str, str]:
    """Run a bash script locally or over ssh. (ok, stdout, reason)."""
    cmd = ["bash", "-s"] if via == "local" else [*SSH, via, "bash", "-s"]
    try:
        r = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, "", f"{via}: {type(e).__name__}"
    if r.returncode != 0:
        return False, "", f"{via}: exit {r.returncode} {r.stderr.strip()[:120]}"
    return True, r.stdout, ""


def busy(via: str) -> int | None:
    """Running `claude -p` sessions on the host, or None when it cannot take a lane."""
    ok, out, _ = run_on(via, PROBE)
    m = re.search(r"busy=(\d+) template=(yes|no)", out) if ok else None
    if not m or m.group(2) != "yes":
        return None
    return int(m.group(1))


def pick(loads: list[tuple[str, str, int | None]]) -> tuple[str, str] | None:
    """Least busy eligible host; ties go to the earlier host in RED_MAIN_HOSTS."""
    eligible = [(n, i, name, via) for i, (name, via, n) in enumerate(loads) if n is not None]
    if not eligible:
        return None
    _, _, name, via = min(eligible)
    return name, via


def lane_name(repo: str, episode: str, attempt: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", repo.split("/")[-1].lower()).strip("-")
    return f"red-main-{slug}-{episode}-{attempt}"


def launch(via: str, name: str, brief: str) -> tuple[bool, str]:
    """Write the lane and start run.sh detached. (ok, lane dir or reason)."""
    if not re.fullmatch(r"[a-z0-9-]+", name):
        return False, f"unsafe lane name {name!r}"
    b64 = base64.b64encode(brief.encode()).decode()
    script = (f'set -e; J="$HOME/agent-work/{name}"; [ ! -e "$J" ] || {{ echo "exists $J" >&2; exit 4; }}\n'
              'mkdir -p "$J/tmp"\n'
              f'echo "{b64}" | base64 --decode > "$J/brief.md"\n'
              'cp "$HOME/agent-work/lib/run-template.sh" "$J/run.sh"; chmod +x "$J/run.sh"\n'
              'nohup "$J/run.sh" </dev/null >/dev/null 2>&1 &\n'
              'echo "LANE=$J"\n')
    ok, out, why = run_on(via, script)
    m = re.search(r"LANE=(.+)", out) if ok else None
    return (True, m.group(1).strip()) if m else (False, why or "no lane path returned")


def lane_state(via: str, lane_dir: str) -> str | None:
    """The run-template status file's state (queued/running/finished/REFUSED...), or None."""
    if not lane_dir or "'" in lane_dir:
        return None
    script = ('S="$HOME/agent-work/status/$(echo \'' + lane_dir + '\' | sed "s#^$HOME/agent-work/##; s#/#__#g").status"; '
              '[ -f "$S" ] && sed -n "s/^state=//p" "$S" || echo "state-missing"')
    ok, out, _ = run_on(via, script)
    return out.strip() or None if ok else None
