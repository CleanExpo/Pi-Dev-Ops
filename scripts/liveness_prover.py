#!/usr/bin/env python3
"""Prove the estate is alive. Do not ask whether it errored.

WHY THIS EXISTS
---------------
On 2026-08-14 GitHub Actions stopped allocating runners to this repo (free-tier
minutes exhausted). Nothing noticed for four days. The reason is structural, not
an oversight, and it is worth stating exactly because the same shape recurs:

  1. Every monitor lived INSIDE the failure domain it monitored. All 12 scheduled
     workflows run on Actions. When Actions died, the monitors died with it.
  2. A job that never runs emits no failure CONTENT. `runner_name` is "", `steps`
     is 0, the run lasts 3 seconds, and there are no logs. Nothing to alert on.
  3. `fail-open-check.yml` — the guard against fail-open conditions — itself
     failed open, for the same reason.
  4. `in.unite-group.hermes-heartbeat` had a plist on disk pointing at a script
     that is a tombstone (`exit 78`), and the agent was not even loaded. Three
     layers of looking-configured over zero monitoring.
  5. `/health` contains no reference to actions, workflows or runners. It answers
     "is the database reachable", which stays true while execution is dead.

The common defect: **the estate monitors error, and a dead component emits the
same signal as a healthy one — silence.**

THE INVERSION
-------------
Every probe here must produce POSITIVE evidence that work happened recently, with
a freshness bound. A probe that cannot prove liveness returns DEAD, never OK.
"I could not check" is a failure, not a pass. That single inversion is the whole
design; everything else is bookkeeping.

This runs OUTSIDE GitHub Actions by construction — it is invoked from a local
LaunchAgent — so it cannot share a failure domain with the thing it checks.

SELF-VERIFICATION
-----------------
A prover nobody proves is the next hermes-heartbeat. Two defences:

  * `--self-test` plants a synthetic dead state and asserts the prover reports it.
    A prover that cannot fail is not evidence. Run it in CI and by hand.
  * The `self` probe reads the prover's own last-run stamp. If this file stops
    running, the NEXT run says so — and if it never runs again, the stamp goes
    stale and any reader can see it.

Usage:
    python3 scripts/liveness_prover.py              # human-readable
    python3 scripts/liveness_prover.py --json       # machine-readable
    python3 scripts/liveness_prover.py --self-test  # prove the prover can fail

Exit codes: 0 all alive · 1 at least one DEAD · 2 self-test failed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STAMP = Path.home() / ".claude" / "liveness-prover-last-run.json"

ALIVE, DEAD = "ALIVE", "DEAD"


@dataclass
class Probe:
    name: str
    state: str
    evidence: str
    remedy: str = ""

    @property
    def ok(self) -> bool:
        return self.state == ALIVE


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    """Run a command. A failure to run is itself information, never swallowed."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]} not installed"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:                                    # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


# ── probes ──────────────────────────────────────────────────────────────────

def probe_ci_executes(repo: str, max_age_h: int = 48) -> Probe:
    """ALIVE only if a run was ASSIGNED A RUNNER recently.

    Conclusion is deliberately ignored. A red run that executed proves the CI
    substrate is alive; that is what this probe is for. A run with an empty
    runner_name executed nothing, which is the condition that hid for four days.
    """
    rc, out = _run([
        "gh", "run", "list", "--repo", repo, "--limit", "20",
        "--json", "databaseId,createdAt",
    ])
    if rc != 0:
        return Probe("ci_executes", DEAD, f"cannot list runs: {out[:160]}",
                     "check gh auth, then re-run")
    try:
        runs = json.loads(out)
    except Exception:
        return Probe("ci_executes", DEAD, "unparseable run list", "check gh version")
    if not runs:
        return Probe("ci_executes", DEAD, "no runs at all", "no workflow has ever run")

    cutoff = time.time() - max_age_h * 3600
    for r in runs:
        rc2, out2 = _run([
            "gh", "api", f"/repos/{repo}/actions/runs/{r['databaseId']}/jobs",
            "--jq", ".jobs[] | .runner_name",
        ])
        if rc2 != 0:
            continue
        names = [n for n in out2.splitlines() if n.strip() and n.strip() != "null"]
        created = time.mktime(time.strptime(r["createdAt"][:19], "%Y-%m-%dT%H:%M:%S"))
        if names and created >= cutoff:
            return Probe("ci_executes", ALIVE,
                         f"run {r['databaseId']} got runner {names[0]!r}")
        if names:
            age_h = int((time.time() - created) / 3600)
            return Probe("ci_executes", DEAD,
                         f"last real execution was {age_h}h ago (run {r['databaseId']})",
                         "Actions minutes likely exhausted — see RA-7274")

    return Probe("ci_executes", DEAD,
                 f"no runner assigned in the last {len(runs)} runs",
                 "Actions minutes exhausted — jobs die in ~3s with runner_name=''")


def probe_launchagent(label: str) -> Probe:
    """ALIVE only if the agent is LOADED and its last exit was 0.

    A plist on disk proves nothing: hermes-heartbeat had one, pointing at a
    tombstone, and was not loaded.
    """
    rc, out = _run(["launchctl", "list"])
    if rc != 0:
        return Probe(f"agent:{label}", DEAD, "launchctl unavailable", "run as the login user")
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].strip() == label:
            status = parts[1].strip()
            if status == "0":
                return Probe(f"agent:{label}", ALIVE, "loaded, last exit 0")
            return Probe(f"agent:{label}", DEAD, f"loaded but last exit {status}",
                         f"launchctl print gui/$UID/{label} for the reason")
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if plist.exists():
        return Probe(f"agent:{label}", DEAD,
                     "plist on disk but NOT loaded — configured, not running",
                     f"launchctl bootstrap gui/$UID {plist}")
    return Probe(f"agent:{label}", DEAD, "no plist and not loaded", "not installed")


def probe_jsonl_fresh(name: str, rel: str, max_age_h: int) -> Probe:
    """ALIVE only if an append-only log gained a line recently.

    This is the cheapest honest liveness signal a loop can emit: it writes when it
    works, so staleness is proof it stopped.
    """
    p = REPO / rel
    if not p.exists():
        return Probe(name, DEAD, f"{rel} does not exist", "the writer has never run")
    age_h = (time.time() - p.stat().st_mtime) / 3600
    if age_h <= max_age_h:
        return Probe(name, ALIVE, f"{rel} written {age_h:.1f}h ago")
    return Probe(name, DEAD, f"{rel} last written {age_h:.1f}h ago (limit {max_age_h}h)",
                 "the loop that appends here has stopped")


def probe_not_tombstone(name: str, script: Path) -> Probe:
    """DEAD if a scheduled script is a tombstone that exits non-zero immediately.

    Added because hermes-heartbeat's script does exactly that, and every layer
    above it looked correctly configured.
    """
    if not script.exists():
        return Probe(name, DEAD, f"{script} missing", "the agent points at nothing")
    body = script.read_text(errors="replace")
    if "exit 78" in body or "tombstone" in body.lower() or "retired" in body.lower():
        return Probe(name, DEAD, f"{script.name} is a tombstone — runs, does nothing",
                     "build the replacement or unload the agent; do not leave both")
    return Probe(name, ALIVE, f"{script.name} is not a tombstone")


def probe_alert_channel_armed() -> Probe:
    """DEAD if the estate cannot tell anyone that something broke.

    This is the highest-leverage probe here, because if the alarm cannot sound
    then no other monitoring matters. `app/server/autonomy.py:184` reads:

        token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
        if not token or not chat_id:
            return                      # <- silent

    So the RA-1973 watchdog dutifully counts poller crashes, calls the alerter,
    and the alerter returns quietly because it has no way to alert. Observed
    2026-08-19 with real `model_timeout` and `RuntimeError` entries sitting in
    .harness/autonomy.jsonl that nobody was ever told about.

    Presence of the variables is all that is checked. Whether the token is VALID
    is a different claim and needs a real send — deliberately not done here,
    because a monitor that messages the founder on every tick is its own problem.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
    if token and chat:
        return Probe("alert_channel_armed", ALIVE,
                     "TELEGRAM_BOT_TOKEN and TELEGRAM_ALERT_CHAT_ID both present")
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token),
                              ("TELEGRAM_ALERT_CHAT_ID", chat)) if not v]
    return Probe("alert_channel_armed", DEAD,
                 f"unset: {', '.join(missing)} — every alert returns silently",
                 "set both in the backend environment; until then failures are unreported")


def probe_self(max_age_h: int = 25) -> Probe:
    """Report the prover's own previous run, then stamp this one.

    If this file stops being run, the next run says so; if it is never run again,
    the stamp goes stale and any reader can see the prover itself died.
    """
    prev = None
    if STAMP.exists():
        try:
            prev = json.loads(STAMP.read_text()).get("ts")
        except Exception:
            prev = None
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps({"ts": time.time(),
                                 "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
    if prev is None:
        return Probe("self", DEAD, "no previous run recorded — first run or stamp lost",
                     "expected on first run; a DEAD here twice means the agent is not firing")
    age_h = (time.time() - prev) / 3600
    if age_h <= max_age_h:
        return Probe("self", ALIVE, f"previous run {age_h:.1f}h ago")
    return Probe("self", DEAD, f"previous run {age_h:.1f}h ago (limit {max_age_h}h)",
                 "the prover's own schedule has stopped firing")


# ── orchestration ───────────────────────────────────────────────────────────

def run_all() -> list[Probe]:
    return [
        probe_ci_executes("CleanExpo/Pi-Dev-Ops"),
        probe_jsonl_fresh("autonomy_polls", ".harness/autonomy.jsonl", 24),
        probe_launchagent("com.phillmcgurk.claude-continuous"),
        probe_launchagent("in.unite-group.hermes-heartbeat"),
        probe_not_tombstone(
            "heartbeat_not_tombstone",
            Path.home() / "Unite-Group/apps/autopilot-runner/scripts/heartbeat-launchd.sh",
        ),
        probe_alert_channel_armed(),
        probe_self(),
    ]


def self_test() -> int:
    """Prove the prover can report DEAD. A control that cannot fire is not a control."""
    checks: list[tuple[str, bool]] = []

    missing = probe_jsonl_fresh("t", "definitely/not/here.jsonl", 24)
    checks.append(("missing file -> DEAD", missing.state == DEAD))

    stale = REPO / ".liveness-selftest-stale.tmp"
    stale.write_text("x")
    os.utime(stale, (time.time() - 99 * 3600,) * 2)
    st = probe_jsonl_fresh("t", stale.name, 1)
    checks.append(("stale file -> DEAD", st.state == DEAD))

    fresh = probe_jsonl_fresh("t", stale.name, 200)
    checks.append(("fresh-enough file -> ALIVE", fresh.state == ALIVE))
    stale.unlink(missing_ok=True)

    tomb = REPO / ".liveness-selftest-tomb.sh"
    tomb.write_text("#!/bin/bash\nexit 78\n")
    checks.append(("tombstone -> DEAD",
                   probe_not_tombstone("t", tomb).state == DEAD))
    tomb.write_text("#!/bin/bash\necho doing real work\n")
    checks.append(("real script -> ALIVE",
                   probe_not_tombstone("t", tomb).state == ALIVE))
    tomb.unlink(missing_ok=True)

    checks.append(("absent agent -> DEAD",
                   probe_launchagent("com.example.definitely.not.loaded").state == DEAD))

    # Both directions of the alert probe, since it is the one that matters most.
    saved = (os.environ.pop("TELEGRAM_BOT_TOKEN", None),
             os.environ.pop("TELEGRAM_ALERT_CHAT_ID", None))
    checks.append(("unarmed alert channel -> DEAD",
                   probe_alert_channel_armed().state == DEAD))
    os.environ["TELEGRAM_BOT_TOKEN"] = "selftest-not-a-real-token"
    os.environ["TELEGRAM_ALERT_CHAT_ID"] = "selftest"
    checks.append(("armed alert channel -> ALIVE",
                   probe_alert_channel_armed().state == ALIVE))
    for k, v in zip(("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALERT_CHAT_ID"), saved):
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    if failed:
        print(f"\nSELF-TEST FAILED: {len(failed)} case(s) — this prover cannot be trusted.")
        return 2
    print(f"\nSELF-TEST PASSED: {len(checks)} cases, both directions proven.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    probes = run_all()
    dead = [p for p in probes if not p.ok]

    if args.json:
        print(json.dumps({
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "verdict": "DEAD" if dead else "ALIVE",
            "dead_count": len(dead),
            "probes": [asdict(p) for p in probes],
        }, indent=2))
        return 1 if dead else 0

    print(f"Liveness — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    for p in probes:
        mark = "OK  " if p.ok else "DEAD"
        print(f"  [{mark}] {p.name}")
        print(f"         {p.evidence}")
        if not p.ok and p.remedy:
            print(f"         -> {p.remedy}")
    print()
    if dead:
        print(f"VERDICT: DEAD — {len(dead)} of {len(probes)} probes cannot prove liveness.")
        return 1
    print(f"VERDICT: ALIVE — all {len(probes)} probes proved recent work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
