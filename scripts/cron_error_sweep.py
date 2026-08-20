#!/usr/bin/env python3
"""Daily sweep for cron jobs sitting in an error state, across every Hermes cron store.

RA-7310. Eight jobs were failing silently — one since 13 May — because the only thing
watching was a per-job watchdog that delivered to `origin`, where nobody reads.

Two design choices are deliberate and load-bearing:

1. **Exits 0 even when it finds failures.** The watchdog this replaces signalled a breach
   with `exit 1`, which set its own `last_status` to `error` — so the alarm about the
   unread pile ended up in the unread pile, indistinguishable from what it was reporting.
   Findings travel on stdout, which Hermes delivers; the exit code stays clean.

2. **Stores are discovered, not listed.** The original RA-7302/7309 sweeps read
   `~/.hermes/cron/jobs.json` and stopped, missing `profiles/empire/cron/jobs.json`
   entirely. Globbing means a new profile is covered the day it is created.

Silent when everything is healthy — Hermes skips delivery on empty stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERMES_ROOT = Path.home() / ".hermes"


def discover_stores(root: Path) -> list[tuple[str, Path]]:
    """Every cron store under a Hermes root: the default one plus each profile's."""
    stores: list[tuple[str, Path]] = []
    default = root / "cron" / "jobs.json"
    if default.is_file():
        stores.append(("default", default))
    for profile_dir in sorted((root / "profiles").glob("*")):
        candidate = profile_dir / "cron" / "jobs.json"
        if candidate.is_file():
            stores.append((profile_dir.name, candidate))
    return stores


def _age_days(stamp: str | None) -> int | None:
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(when.tzinfo) - when).days


def failing_jobs(stores: list[tuple[str, Path]]) -> list[dict]:
    found: list[dict] = []
    for label, path in stores:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # An unreadable store is itself a finding — never a silent pass.
            found.append({
                "store": label, "id": "-", "name": f"UNREADABLE STORE {path}",
                "age": None, "kind": "UNREADABLE", "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        jobs = raw.get("jobs", raw) if isinstance(raw, dict) else raw
        for job in jobs:
            status_bad = job.get("last_status") == "error"
            # A job can run perfectly and still fail to reach anyone. Hermes records that
            # in last_delivery_error while leaving last_status "ok" — so a delivery failure
            # is invisible to a status-only check. Found the hard way: this sweep's own
            # first live run reported ok while its Telegram delivery had failed outright.
            delivery_bad = bool(job.get("last_delivery_error"))
            if not (status_bad or delivery_bad):
                continue
            if status_bad and delivery_bad:
                kind, detail = "RAN=error DELIVERY=failed", (
                    f"{job.get('last_error')} | delivery: {job.get('last_delivery_error')}")
            elif status_bad:
                kind, detail = "RAN=error", job.get("last_error")
            else:
                kind, detail = "UNDELIVERED (ran ok)", job.get("last_delivery_error")
            found.append({
                "store": label,
                "id": job.get("id", "?"),
                "name": job.get("name", "?"),
                "age": _age_days(job.get("last_run_at")),
                "kind": kind,
                "error": " ".join(str(detail or "").split())[:150],
            })
    found.sort(key=lambda f: (-(f["age"] if f["age"] is not None else -1), f["store"]))
    return found


def render(found: list[dict]) -> str:
    if not found:
        return ""
    lines = [f"{len(found)} cron job(s) failing or undelivered:", ""]
    for f in found:
        age = "never run" if f["age"] is None else f"{f['age']}d ago"
        lines.append(f"• [{f['store']}] {f['name']} ({f['id']}) — {f['kind']}, last ran {age}")
        lines.append(f"    {f['error']}")
    lines.append("")
    lines.append("Fix or disable each one. A job left failing is a job nobody is watching,")
    lines.append("and an UNDELIVERED job ran fine while telling no one.")
    return "\n".join(lines)


def self_test() -> int:
    """Prove the check fires. A sweep that has never been watched failing is not a control."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "cron").mkdir(parents=True)
        (root / "profiles" / "fake" / "cron").mkdir(parents=True)
        (root / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
            {"id": "healthy01", "name": "fine", "last_status": "ok"},
        ]}))
        (root / "profiles" / "fake" / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
            {"id": "broken01", "name": "planted failure", "last_status": "error",
             "last_run_at": "2026-01-01T00:00:00+10:00", "last_error": "synthetic"},
        ]}))
        found = failing_jobs(discover_stores(root))

        ok = len(found) == 1 and found[0]["id"] == "broken01"
        print("SELF-TEST: detects a planted failure in a PROFILE store ..."
              f" {'PASS' if ok else 'FAIL'}")
        if not ok:
            print(f"  expected exactly broken01, got {[f['id'] for f in found]}")
            return 1

        # The blind spot this sweep shipped with for ten minutes: a job that RAN fine and
        # failed to reach anyone. last_status is "ok", so a status-only check calls it
        # healthy. Watched failing here so the fix cannot silently regress.
        (root / "profiles" / "fake" / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
            {"id": "undeliv01", "name": "ran fine, told nobody", "last_status": "ok",
             "last_run_at": "2026-08-01T00:00:00+10:00",
             "last_delivery_error": "python-telegram-bot not installed"},
        ]}))
        found = failing_jobs(discover_stores(root))
        ok2 = len(found) == 1 and found[0]["id"] == "undeliv01" and "UNDELIVERED" in found[0]["kind"]
        print(f"SELF-TEST: detects ran-ok-but-UNDELIVERED ... {'PASS' if ok2 else 'FAIL'}")
        if not ok2:
            print(f"  expected undeliv01/UNDELIVERED, got {[(f['id'], f.get('kind')) for f in found]}")
            return 1

        # Negative control: a clean estate must stay silent, or the sweep is just noise.
        (root / "profiles" / "fake" / "cron" / "jobs.json").write_text(
            json.dumps({"jobs": [{"id": "b", "name": "fixed", "last_status": "ok"}]}))
        quiet = render(failing_jobs(discover_stores(root)))
        print(f"SELF-TEST: silent when clean ... {'PASS' if quiet == '' else 'FAIL'}")
        return 0 if quiet == "" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true",
                    help="prove the sweep detects a planted failure and stays silent when clean")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    report = render(failing_jobs(discover_stores(HERMES_ROOT)))
    if report:
        print(report)
    # Always 0: see the module docstring. The finding is the stdout, not the exit code.
    return 0


if __name__ == "__main__":
    sys.exit(main())
