#!/usr/bin/env python3
"""fleet.py — probe and dispatch across the Nexus compute fleet.

Read-only by default. `probe` measures real capacity and which agent runtimes actually
authenticate on each node; `dispatch` fans a prompt out to chosen nodes and collects results.

Adding a node is one entry in NODES. Nothing else changes.

    fleet.py probe                      # capacity + runtime matrix for every node
    fleet.py probe --json               # machine-readable
    fleet.py health                     # drift per node: autogit, ~/.claude off main, untrusted runtime
    fleet.py dispatch --node mini --prompt-file /tmp/job.md [--timeout 1800]
    fleet.py dispatch --all-remote --prompt-file /tmp/job.md
    fleet.py collect                    # gather finished job outputs
"""
import argparse, json, os, shlex, socket, subprocess, sys, time, uuid

# --- Fleet registry -------------------------------------------------------------
# runtimes: which agent CLIs are USABLE on that node, not merely installed.
#   claude-ssh:  Claude Code CLI authenticates over a non-interactive SSH shell
#   codex-ssh:   Codex CLI runs headless over SSH (always sandboxed)
# Which node is LOCAL is detected at runtime, never hardcoded. It used to be pinned to
# "macbook" with host=None, so a session running on the Mac mini read its own node as
# UNREACHABLE and quoted that as evidence — then tried to ssh into the machine it was already
# running on, seven times, before anyone ran `hostname`. A map that asserts where you are is
# worse than no map, because it is believed. (2026-08-18)
def _local_node() -> str:
    # A managed Claude Code container reports a generic hostname ("vm"), so hostname
    # marks cannot identify it and it would fall through to "" — indistinguishable from
    # an unrecognised laptop. CLAUDE_CODE_CONTAINER_ID is set by the runtime there and by
    # nothing on a workstation, so it is checked FIRST and by presence, never by value.
    if os.environ.get("CLAUDE_CODE_CONTAINER_ID"):
        return "cloud"
    h = socket.gethostname().lower()
    for name, marks in (
        ("mini", ("mac-mini", "macmini")),
        ("macbook", ("macbook",)),
        ("windows", ("desktop", "phill-desktop")),
    ):
        if any(m in h for m in marks):
            return name
    return ""


LOCAL_NODE = _local_node()

NODES = {
    "macbook": {
        "host": "macbook-ts",
        "shell": "zsh -lc",
        "home": "/Users/phill-mac",
        "runtimes": ["claude-local", "codex-local"],
        "notes": "primary dev node",
    },
    "mini": {
        "host": "mini-ts",
        "shell": "zsh -lc",
        "home": "/Users/phill-mac",
        "runtimes": ["codex-ssh"],
        "notes": (
            "review/merge node. Claude CLI CANNOT auth over SSH (login keychain is "
            "GUI-only; launchctl asuser is denied) — use codex-ssh, or run Claude "
            "from the machine itself."
        ),
    },
    "windows": {
        "host": "win-ts",
        "shell": "powershell -NoProfile -Command",
        "home": None,
        "runtimes": [],                     # fill in once it is up and probed
        "notes": "phill-desktop. Add runtimes after the first successful probe.",
    },
    # Ephemeral managed Claude Code container (claude.ai/code and the mobile/web app).
    # It is a real estate member and was invisible here, so `probe` reported a three-node
    # fleet while a fourth surface was doing work nobody could see.
    #
    # local_only is load-bearing. host=None means "run the script locally" (see remote()),
    # so WITHOUT this flag a probe from the MacBook would run CAPACITY on the MacBook and
    # print the MacBook's cores under NODE=cloud -- a map asserting where you are, which
    # this file already records as worse than no map. It is probeable only from inside
    # itself; from anywhere else it reports unreachable with the reason.
    #
    # runtimes is deliberately EMPTY and must stay empty unless something is watched
    # returning output. Verified 2026-08-31 in a live container: no `codex` binary, no
    # ~/.codex, no OPENAI_* env, no OpenRouter key (curl returns 000), and Tailscale is
    # unreachable -- so it can never be an ssh dispatch target. It reaches the estate
    # over GitHub only.
    "cloud": {
        "host": None,
        "shell": "bash -lc",
        "home": None,
        "runtimes": [],
        "local_only": True,
        "reach": "github-only",
        "notes": (
            "managed Claude Code container; ephemeral. No Tailscale, no Codex, no "
            "OpenRouter key. Syncs via GitHub (skills/cloud-node). Never an ssh target."
        ),
    },
}

SSH = ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes"]
JOBDIR = os.path.expanduser("~/.claude/fleet-jobs")


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # unreachable host, missing binary
        return 1, "", str(e)


def remote(node, script, timeout=60):
    """Run a shell snippet on a node. Local nodes skip ssh entirely.

    ssh joins its trailing argv with spaces into ONE remote command string, so the
    script must be quoted as a single token — otherwise `zsh -lc` receives only the
    first word and everything after the first `;` runs in the login shell instead.
    """
    n = NODES[node]
    # Run locally when this IS the local machine, decided by hostname at runtime. Keying this
    # off a hardcoded host=None made a session on the mini ssh to itself and read the result
    # as UNREACHABLE.
    if node == LOCAL_NODE or n["host"] is None:
        # Use the node's OWN shell. This used to be a hardcoded ["zsh", "-lc"], which
        # meant any node without zsh -- a Linux container, a Windows box -- failed its
        # LOCAL probe with "No such file or directory: 'zsh'" and was reported
        # UNREACHABLE. A missing interpreter and a machine that is switched off produce
        # the identical row, which is the failure this file already names: a broken query
        # and a quiet node look the same. (2026-08-31)
        return run(shlex.split(n["shell"]) + [script], timeout)
    wrapped = f"{n['shell']} {shlex.quote(script)}"
    return run(SSH + [n["host"], wrapped], timeout)


# Labelled output — a login shell on a remote node may emit banner lines, so positional
# parsing silently mis-assigns fields (this bit us: the Mini's memsize parsed as cores).
CAPACITY = (
    "echo FLEETCORES=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 0); "
    # hw.memsize is macOS-only. Without the Linux fallback a Linux node reported
    # mem_gb=None while cores and load came back fine -- a half-filled row that reads as
    # a partly-broken machine rather than a probe that only speaks one OS.
    "echo FLEETMEM=$(sysctl -n hw.memsize 2>/dev/null || "
    "awk '/MemTotal/{print $2*1024; exit}' /proc/meminfo 2>/dev/null || echo 0); "
    "echo FLEETLOAD=$(uptime | sed 's/.*load averages*: //' | tr -d ',' | awk '{print $1}')"
)

# The same three facts, in PowerShell. The node table has carried
# `shell: powershell -NoProfile -Command` for the Windows box since it was added, but every
# payload sent through it was POSIX -- sysctl, nproc, uptime, $(...), 2>/dev/null. So the
# Windows probe could never have returned a reading, online or not, and "offline since
# 2026-07-20" hid a second fault underneath the first. The skill's own rule (declare a
# runtime only after watching it return output) could not be satisfied for that node by
# construction. (2026-08-31)
CAPACITY_PS = (
    "$c=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors; "
    "$m=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory; "
    "$l=(Get-CimInstance Win32_Processor | "
    "Measure-Object -Property LoadPercentage -Average).Average; "
    "Write-Output \"FLEETCORES=$c\"; Write-Output \"FLEETMEM=$m\"; "
    # LoadPercentage is a percentage across all cores; convert to a load-average-like
    # figure so free_cores means the same thing on every node rather than silently
    # meaning two different things.
    "Write-Output (\"FLEETLOAD=\" + [math]::Round($c * $l / 100, 2))"
)

# Runtime presence, per dialect. Same rule: only ever reports installed-or-not.
RUNTIME_PROBES = {
    "posix": {
        "claude": "claude --version >/dev/null 2>&1 && echo yes || echo no",
        "codex": "codex --version >/dev/null 2>&1 && echo yes || echo no",
    },
    "powershell": {
        "claude": "if (Get-Command claude -EA SilentlyContinue) {'yes'} else {'no'}",
        "codex": "if (Get-Command codex -EA SilentlyContinue) {'yes'} else {'no'}",
    },
}


def dialect(node: str) -> str:
    """Which script language this node's shell actually speaks."""
    return "powershell" if "powershell" in NODES[node]["shell"].lower() else "posix"


def probe_node(name):
    n = NODES[name]
    out = {"node": name, "host": n["host"] or "local", "reachable": False,
           "cores": None, "mem_gb": None, "load1": None, "free_cores": None,
           "runtimes": {}, "notes": n["notes"]}
    # A local_only node has host=None, which remote() reads as "run it here". Probing one
    # from another machine would therefore measure THIS machine and label it with that
    # node's name. Report it honestly instead of inventing a reading.
    if n.get("local_only") and name != LOCAL_NODE:
        out["notes"] = (
            f"{n['notes']} | not probeable from {LOCAL_NODE or 'this host'}: "
            "local_only node, reachable only from inside itself"
        )
        out["runtimes"]["declared"] = n["runtimes"]
        return out
    d = dialect(name)
    rc, so, err = remote(name, CAPACITY_PS if d == "powershell" else CAPACITY, timeout=20)
    if rc != 0 or not so:
        # Say WHY. An empty row was previously indistinguishable between "host is down",
        # "ssh refused" and "the payload could not run there".
        out["error"] = (err or f"no output (rc={rc})")[:200]
        out["runtimes"]["declared"] = n["runtimes"]
        return out
    out["reachable"] = True
    kv = {}
    for line in so.splitlines():
        if "=" in line and line.strip().startswith("FLEET"):
            k, _, v = line.strip().partition("=")
            kv[k] = v.strip()
    try:
        out["cores"] = int(kv.get("FLEETCORES", 0)) or None
        mem = int(kv.get("FLEETMEM", 0))
        out["mem_gb"] = round(mem / 1024**3) if mem else None
        out["load1"] = float(kv.get("FLEETLOAD", 0))
        if out["cores"]:
            out["free_cores"] = max(0.0, round(out["cores"] - out["load1"], 1))
    except ValueError:
        pass

    # Runtime auth is the thing that actually decides where work can go.
    for k, cmd in RUNTIME_PROBES[d].items():
        rc, so, _ = remote(name, cmd, timeout=25)
        out["runtimes"][k + "_installed"] = (so.strip() == "yes")
    out["runtimes"]["declared"] = n["runtimes"]
    return out


def cmd_probe(args):
    rows = [probe_node(n) for n in NODES]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'NODE':10} {'REACH':6} {'CORES':6} {'MEM':5} {'LOAD':6} {'FREE':5}  RUNTIMES")
    for r in rows:
        rt = ",".join(r["runtimes"].get("declared") or []) or "-"
        print(f"{r['node']:10} {'yes' if r['reachable'] else 'NO':6} "
              f"{str(r['cores'] or '-'):6} {str(r['mem_gb'] or '-'):5} "
              f"{str(r['load1'] or '-'):6} {str(r['free_cores'] or '-'):5}  {rt}")
    for r in rows:
        if not r["reachable"]:
            print(f"\n  {r['node']}: UNREACHABLE — {r['notes']}")
    total = sum(r["free_cores"] or 0 for r in rows if r["reachable"])
    print(f"\nfleet free capacity: ~{total:.0f} cores across "
          f"{sum(1 for r in rows if r['reachable'])} reachable node(s)")
    return 0


# Machine drift, per node (RA-7802). THIS checkout's checker is streamed to every node on
# stdin, so each node is judged by the current checks rather than by whatever stale copy
# its own ~/.claude holds -- a stale ~/.claude is one of the things being checked.
CHECKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "..", "..", "scripts", "check-enforcement-wiring.py")


def node_health(name):
    n = NODES[name]
    row = {"node": name, "state": "unreachable", "findings": []}
    if n.get("local_only") and name != LOCAL_NODE:
        row.update(state="skipped", findings=["local_only node"])
        return row
    if name == LOCAL_NODE or n["host"] is None:
        cmd = [sys.executable, "-"]
    else:
        cmd = SSH + [n["host"], ("python" if dialect(name) == "powershell" else "python3") + " -"]
    try:
        with open(CHECKER, encoding="utf-8") as f:
            p = subprocess.run(cmd, input=f.read(), capture_output=True, text=True, timeout=90)
    except (subprocess.TimeoutExpired, OSError) as e:
        row["findings"] = [f"could not run the check: {type(e).__name__}"]
        return row
    ran = "registered hook commands" in p.stdout
    row["findings"] = [line.strip() for line in p.stdout.splitlines()
                       if line.strip().startswith(("DRIFT", "MISSING:"))]
    if not ran:  # never read "no output" as "no drift"
        row["findings"] = [f"check did not run (rc={p.returncode}): {(p.stderr or p.stdout)[:160]}"]
        return row
    row["state"] = "ok" if p.returncode == 0 and not row["findings"] else "drift"
    return row


def cmd_health(args):
    rows = [node_health(n) for n in NODES]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['node']:10} {r['state'].upper()}")
            for f in r["findings"]:
                print(f"           - {f}")
    return 0 if all(r["state"] in ("ok", "skipped") for r in rows) else 1


def cmd_dispatch(args):
    targets = args.node or []
    if args.all_remote:
        targets = [n for n in NODES if NODES[n]["host"] is not None]
    if not targets:
        print("no target: pass --node NAME or --all-remote", file=sys.stderr)
        return 2

    prompt = open(args.prompt_file).read()
    os.makedirs(JOBDIR, exist_ok=True)
    launched = []
    for t in targets:
        p = probe_node(t)
        if not p["reachable"]:
            print(f"skip {t}: unreachable")
            continue
        if "codex-ssh" not in NODES[t]["runtimes"] and NODES[t]["host"]:
            print(f"skip {t}: no usable remote runtime declared ({NODES[t]['notes']})")
            continue
        jid = f"{t}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        rprompt, rout = f"/tmp/{jid}.prompt", f"/tmp/{jid}.out"
        subprocess.run(["scp", "-q", args.prompt_file, f"{NODES[t]['host']}:{rprompt}"],
                       check=False)
        # Sandboxed always. A bypassed review is not valid gate evidence.
        # Same ssh-argv trap as remote(): the whole remote command must be ONE quoted token,
        # or ssh's join leaves `zsh -lc` holding just the first word and the job never starts.
        # This silently launched nothing for three jobs before it was caught — the launch
        # returned 0 because ssh itself succeeded.
        inner = (f"cd /tmp && codex exec --sandbox read-only --skip-git-repo-check "
                 f"\"$(cat {rprompt})\" > {rout} 2>&1; echo DONE >> {rout}")
        launcher = f"nohup zsh -c {shlex.quote(inner)} >/dev/null 2>&1 &"
        wrapped = f"{NODES[t]['shell']} {shlex.quote(launcher)}"
        subprocess.run(SSH + [NODES[t]["host"], wrapped], capture_output=True, text=True,
                       timeout=30)
        # Positive control: the job must exist on the remote within a few seconds. A launch
        # that reports success without a running process is the failure mode this catches.
        started = False
        for _ in range(6):
            rc, so, _e = remote(t, f"test -f {rout} && echo YES || pgrep -f 'codex exec' >/dev/null && echo YES || echo NO",
                                timeout=20)
            if "YES" in so:
                started = True
                break
        if not started:
            print(f"FAILED to start on {t}: no output file and no codex process. Job NOT running.")
            continue
        launched.append({"job": jid, "node": t, "remote_out": rout})
        print(f"launched {jid} on {t} -> {rout} (start confirmed)")

    json.dump(launched, open(f"{JOBDIR}/last-dispatch.json", "w"), indent=2)
    print(f"\n{len(launched)} job(s) launched. Collect with: fleet.py collect")
    return 0


def cmd_collect(args):
    path = f"{JOBDIR}/last-dispatch.json"
    if not os.path.exists(path):
        print("no dispatch record found")
        return 1
    for j in json.load(open(path)):
        rc, so, _ = remote(j["node"], f"tail -c 400000 {j['remote_out']} 2>/dev/null", timeout=60)
        done = so.rstrip().endswith("DONE")
        local = f"{JOBDIR}/{j['job']}.out"
        if so:
            open(local, "w").write(so)
            state = "COMPLETE" if done else "RUNNING"
        else:
            # No output file is NOT the same as "still thinking". Distinguish a live process
            # from a job that never started — reporting the latter as RUNNING hides a failure
            # until someone happens to look, which is exactly what happened on 2026-07-29.
            _rc, alive, _e = remote(j["node"], "pgrep -f 'codex exec' >/dev/null && echo ALIVE || echo DEAD",
                                    timeout=20)
            state = "RUNNING (no output yet)" if "ALIVE" in alive else "NEVER STARTED — job is not running"
        print(f"\n=== {j['job']} [{state}] -> {local if so else '(nothing)'}")
        if so:
            print("\n".join(so.splitlines()[-25:]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_probe)
    h = sub.add_parser("health"); h.add_argument("--json", action="store_true")
    h.set_defaults(fn=cmd_health)
    d = sub.add_parser("dispatch")
    d.add_argument("--node", action="append")
    d.add_argument("--all-remote", action="store_true")
    d.add_argument("--prompt-file", required=True)
    d.set_defaults(fn=cmd_dispatch)
    c = sub.add_parser("collect"); c.set_defaults(fn=cmd_collect)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
