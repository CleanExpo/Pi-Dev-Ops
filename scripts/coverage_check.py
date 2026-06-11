#!/usr/bin/env python3
"""coverage_check.py — honest Definition-of-Done coverage for a project.

Reads a DoD spec (.harness/dod/<project>.dod.yaml), runs each requirement's
probe against the real repo, and prints a status you can trust because every
line is backed by something the machine actually observed.

The design rule that makes this honest:

    Items the machine CANNOT verify are reported as UNKNOWN and are NEVER
    counted toward "done". The headline percentage is computed ONLY over
    machine-checkable items (PASS / FAIL). UNKNOWN items are listed
    separately as "needs your confirmation". Nothing is ever guessed.

This is the opposite of a status report that says "48% done" by quietly
treating everything it didn't check as finished.

Probe types (in the DoD `check:` field):
    command                cmd: <shell>  [expect_exit: 0]  [timeout: 120]
                           the real oracle: run a test/typecheck/lint/assertion;
                           PASS only when exit code matches. Use expect_exit: 1
                           for negative tests that prove a gate fails closed.
    http                   url: <url>  [expect_status: 200]  [contains: <str>]
                           live smoke test; UNKNOWN (not FAIL) if unreachable.
    path_exists            path: <repo-relative path>
    registry_has_project   project_id: <id>  (checks .harness/projects.json)
    glob_grep              glob: <glob>  pattern: <regex>
    human                  (always UNKNOWN unless attested — see below)

SAFETY: `command` probes execute shell. Only run DoD specs you trust (your own,
in your own repo). This is a verification harness for your projects, by design.

Human attestation (optional): .harness/dod/attestations.yaml
    ra-30-design-team: {confirmed: true, by: "Phill", date: "2026-06-10", note: "..."}
A human item is only PASS if you explicitly confirm it there. This keeps the
human in the loop without letting the machine invent progress.

Usage:
    python scripts/coverage_check.py .harness/dod/restoreassist.dod.yaml
    python scripts/coverage_check.py .harness/dod/restoreassist.dod.yaml --repo /path/to/repo
    python scripts/coverage_check.py .harness/dod/restoreassist.dod.yaml --json

Exit code is always 0 — this is a report, not a gate. (A gate that blocks the
build on coverage is a later phase; first you need to trust the number.)
"""
from __future__ import annotations

import argparse
import glob as globlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: needs pyyaml. install with: pip install pyyaml --break-system-packages",
          file=sys.stderr)
    raise SystemExit(2)

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_attestations(repo: Path) -> dict:
    p = repo / ".harness" / "dod" / "attestations.yaml"
    if p.exists():
        data = _load_yaml(p)
        return data if isinstance(data, dict) else {}
    return {}


def probe_path_exists(repo: Path, req: dict) -> tuple[str, str]:
    rel = req.get("path", "")
    target = repo / rel
    if target.exists():
        return PASS, f"exists: {rel}"
    return FAIL, f"missing: {rel}"


def probe_registry(repo: Path, req: dict) -> tuple[str, str]:
    pid = req.get("project_id", "")
    reg = repo / ".harness" / "projects.json"
    if not reg.exists():
        return UNKNOWN, "projects.json not found — cannot verify"
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        return UNKNOWN, f"projects.json unreadable: {exc}"
    found = any(p.get("id") == pid for p in data.get("projects", []))
    return (PASS, f"'{pid}' present in projects.json") if found else (FAIL, f"'{pid}' not in projects.json")


def probe_glob_grep(repo: Path, req: dict) -> tuple[str, str]:
    pattern = re.compile(req.get("pattern", "."))
    matches = globlib.glob(str(repo / req.get("glob", "")), recursive=True)
    files = [m for m in matches if Path(m).is_file()]
    if not files:
        return FAIL, f"no files match glob: {req.get('glob')}"
    for f in files:
        try:
            if pattern.search(Path(f).read_text(encoding="utf-8", errors="ignore")):
                return PASS, f"pattern found in {Path(f).name}"
        except OSError:
            continue
    # pattern '.' against existing files means "any file present" → PASS handled above;
    # here no content matched
    return FAIL, f"{len(files)} file(s) matched glob but not pattern {req.get('pattern')!r}"


def probe_human(repo: Path, req: dict, attest: dict) -> tuple[str, str]:
    rid = req.get("id")
    a = attest.get(rid)
    if isinstance(a, dict) and a.get("confirmed") is True:
        by = a.get("by", "?")
        note = a.get("note", "")
        return PASS, f"human-attested by {by}" + (f": {note}" if note else "")
    return UNKNOWN, "needs your confirmation (no attestation on file)"


def probe_command(repo: Path, req: dict) -> tuple[str, str]:
    """Run a shell command in the repo. PASS when exit code == expect_exit.

    This is the real oracle: a test runner, a type-checker, a linter, or a
    one-off assertion script. 'done' is an exit code, not a model's opinion.
    expect_exit defaults to 0; set it (e.g. 1) for negative tests that prove
    a gate fails closed on bad input.
    """
    cmd = req.get("cmd", "")
    if not cmd:
        return UNKNOWN, "no cmd specified"
    expect = int(req.get("expect_exit", 0))
    timeout = int(req.get("timeout", 120))
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(repo),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return FAIL, f"timed out after {timeout}s running: {cmd[:60]}"
    except OSError as exc:
        return UNKNOWN, f"could not run command: {exc}"
    out = (proc.stdout + proc.stderr).strip().splitlines()
    last = out[-1][:120] if out else "(no output)"
    status = PASS if proc.returncode == expect else FAIL
    return status, f"exit {proc.returncode} (expected {expect}) — {last}"


def probe_http(repo: Path, req: dict) -> tuple[str, str]:
    """Hit a URL. PASS when status == expect_status (and body contains
    `contains`, if given). A live smoke test — the strongest 'is it actually
    deployed and answering' signal. If the host is unreachable, returns
    UNKNOWN (cannot verify), never a false FAIL."""
    url = req.get("url", "")
    if not url:
        return UNKNOWN, "no url specified"
    expect = int(req.get("expect_status", 200))
    contains = req.get("contains")
    timeout = int(req.get("timeout", 15))
    method = req.get("method", "GET").upper()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, method=method), timeout=timeout
        ) as resp:
            status = resp.status
            body = resp.read(4096).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        status, body = exc.code, ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UNKNOWN, f"could not reach {url}: {exc} (cannot verify)"
    if status != expect:
        return FAIL, f"{method} {url} -> {status} (expected {expect})"
    if contains and contains not in body:
        return FAIL, f"{status} but body missing {contains!r}"
    return PASS, f"{method} {url} -> {status}" + (f", contains {contains!r}" if contains else "")


PROBES = {
    "path_exists": probe_path_exists,
    "registry_has_project": probe_registry,
    "glob_grep": probe_glob_grep,
    "command": probe_command,
    "http": probe_http,
}


def evaluate(dod: dict, repo: Path) -> list[dict]:
    attest = _load_attestations(repo)
    results = []
    for req in dod.get("requirements", []):
        check = req.get("check")
        if check == "human":
            status, evidence = probe_human(repo, req, attest)
        elif check in PROBES:
            status, evidence = PROBES[check](repo, req)
        else:
            status, evidence = UNKNOWN, f"unknown check type {check!r}"
        results.append({
            "id": req.get("id"), "horizon": req.get("horizon"),
            "statement": req.get("statement"), "check": check,
            "status": status, "evidence": evidence,
        })
    return results


def report(dod: dict, results: list[dict]) -> dict:
    auto = [r for r in results if r["status"] in (PASS, FAIL)]
    passed = [r for r in auto if r["status"] == PASS]
    failed = [r for r in auto if r["status"] == FAIL]
    unknown = [r for r in results if r["status"] == UNKNOWN]
    pct = (len(passed) / len(auto) * 100) if auto else 0.0
    return {
        "project_id": dod.get("project_id"),
        "machine_checkable": len(auto),
        "passed": len(passed),
        "failed": len(failed),
        "unknown_needs_confirmation": len(unknown),
        "verifiable_coverage_pct": round(pct, 1),
        "results": results,
    }


def print_human(rep: dict) -> None:
    icon = {PASS: "[PASS]", FAIL: "[FAIL]", UNKNOWN: "[ ?? ]"}
    print(f"\nDefinition-of-Done coverage — {rep['project_id']}")
    print("=" * 64)
    for r in rep["results"]:
        print(f"{icon[r['status']]} {r['id']:<22} ({r['horizon']})")
        print(f"        {r['statement']}")
        print(f"        → {r['evidence']}")
    print("-" * 64)
    print(f"Machine-checkable items: {rep['machine_checkable']} "
          f"({rep['passed']} pass, {rep['failed']} fail)")
    print(f"VERIFIABLE COVERAGE: {rep['verifiable_coverage_pct']}%  "
          f"(of machine-checkable items only)")
    print(f"NEEDS YOUR CONFIRMATION (not counted as done): "
          f"{rep['unknown_needs_confirmation']} item(s)")
    print("\nThis number reflects only what the machine could actually verify.")
    print("UNKNOWN items are real work whose status only you can confirm —")
    print("they are deliberately NOT folded into the percentage.\n")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Honest Definition-of-Done coverage report")
    ap.add_argument("dod", help="path to a .dod.yaml spec")
    ap.add_argument("--repo", default=None, help="repo root to probe (default: 3 levels up from the dod file, i.e. repo root)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the human report")
    args = ap.parse_args(argv)

    dod_path = Path(args.dod).resolve()
    if not dod_path.exists():
        print(f"error: DoD spec not found: {dod_path}", file=sys.stderr)
        return 2
    # default repo root: the dod lives at <repo>/.harness/dod/<file>, so go up 3
    repo = Path(args.repo).resolve() if args.repo else dod_path.parents[2]

    dod = _load_yaml(dod_path)
    results = evaluate(dod, repo)
    rep = report(dod, results)

    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print_human(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
