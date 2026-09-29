#!/usr/bin/env python3
"""Decide whether a reviewer report may be ACTED ON. Not whether it says PASS.

Written because 'title is not Provisional', 'filter count is 0' and 'head_sha matches'
check naming and binding only. A report that is truncated, corrupted, structurally empty,
or left over from an earlier run satisfies all three and still is not a result.

Exit 0 = the report is a usable verdict (read `verdict` for which way it went).
Exit 1 = not actionable; the reason says what is missing. Never treat exit 1 as a FAIL.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _load_gate():
    """The checklist has ONE owner. Two copies of eight ids drift, and the brief's
    own header records what drift between brief and schema already cost."""
    path = Path(__file__).resolve().parent / "pr_release_gate.py"
    spec = importlib.util.spec_from_file_location("pr_release_gate_for_verdict", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

EXPECTED_DIMENSIONS = ["architecture", "correctness", "security", "tests",
                       "error-handling", "duplication", "conventions"]

# WHAT A FINDING MUST CARRY, and why two of these are pairs (2026-08-13).
#
# This tuple used to be flat: title, severity, file, demonstration, required_fix.
# Nothing documented it — not reviewer-brief.md, not reviewer-report-schema.md —
# and every reviewer report ever written in this estate (ten on disk under
# .spm/reviewer-report-*.json) uses `reproduction` and `suggested_fix` instead.
# Review 14 was rejected on all 16 findings for it, with the substance intact and
# every citation anchored: the recorder was enforcing a vocabulary that appeared
# in no brief and no report.
#
# Named as alternatives rather than renamed, because both spellings now exist in
# reports on disk and neither is wrong. The requirement is unchanged and
# unweakened: a finding must still say how it was DEMONSTRATED and what would FIX
# it, under one of the two accepted names, non-empty.
REQUIRED_FINDING_FIELDS = ("title", "severity", "file")
REQUIRED_FINDING_ALTERNATIVES = (
    ("reproduction", "demonstration"),
    ("suggested_fix", "required_fix"),
)


def check(report_path: str, log_path: str, expected_head: str, repo: str) -> list[str]:
    problems = []

    # 1. Readable and syntactically whole. Catches truncation and partial writes.
    try:
        raw = open(report_path).read()
    except OSError as e:
        return [f"report unreadable: {e}"]
    if not raw.strip():
        return ["report is empty"]
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"report is not valid JSON (truncated or corrupt): {e}"]

    # 2. Bound to the exact head, in full.
    head = d.get("head_sha") or ""
    if head != expected_head:
        problems.append(f"head_sha {head!r} != expected {expected_head!r}")

    # 3. Not the provisional first write.
    findings = d.get("blocking_findings") or []
    titles = [(f.get("title") or "") for f in findings]
    if any(t.upper().startswith("PROVISIONAL") for t in titles):
        problems.append("still carries the provisional blocker — the run did not finish")

    # 4. A verdict at all, and a coherent one.
    verdict = d.get("verdict")
    if verdict not in ("PASS", "FAIL"):
        problems.append(f"verdict {verdict!r} is not PASS or FAIL")
    if verdict == "PASS" and findings:
        problems.append("PASS with blocking findings is incoherent")
    if verdict == "FAIL" and not findings:
        problems.append("FAIL with no blocking findings gives nothing to act on")

    # 5. The reviewer covered its contract rather than writing a stub.
    #
    # Schema 1 checked this against a CONSTANT — the seven strings below — which a
    # reviewer discharged by copying them out of the schema example. Five rounds on
    # one branch declared byte-identical dimensions while returning 3, 2, 1, 11 and
    # 11 findings, so the field carried no information about what was read. Schema 2
    # replaces it with a per-item checklist and a coverage ledger checked against the
    # real diff (pr_release_gate.check_review_checklist / check_review_coverage).
    #
    # A PASS must be schema 2: it is the verdict that releases code. A FAIL may still
    # be schema 1, because a FAIL's payload is its findings and every drain loop in
    # flight across the estate keeps working.
    schema = d.get("schema")
    if verdict == "PASS" and schema != gate.REVIEW_SCHEMA:
        problems.append(
            f"PASS carries schema {schema!r}; a releasing verdict requires schema "
            f"{gate.REVIEW_SCHEMA} with `checklist` and `coverage`")
    elif schema == gate.REVIEW_SCHEMA:
        try:
            gate.check_review_checklist(d)
            gate.check_review_coverage(
                d, gate.changed_files(Path(repo), d.get("base_sha") or "",
                                      expected_head))
        except (ValueError, subprocess.SubprocessError, OSError) as e:
            problems.append(str(e))
    else:
        dims = d.get("reviewed_dimensions") or []
        if list(dims) != EXPECTED_DIMENSIONS:
            problems.append(f"reviewed_dimensions is not the standard seven: {dims}")

    # 6. Every finding is actionable. A finding without a demonstration is an opinion.
    for i, f in enumerate(findings, 1):
        for field in REQUIRED_FINDING_FIELDS:
            if not (f.get(field) or "").strip():
                problems.append(f"finding {i} has empty {field}")
        for names in REQUIRED_FINDING_ALTERNATIVES:
            if not any((f.get(n) or "").strip() for n in names):
                problems.append(
                    f"finding {i} carries none of {' / '.join(names)}")

    # 7. Not a stale artefact from an earlier run: the report must be newer than the
    #    commit it claims to review.
    try:
        commit_epoch = int(subprocess.run(
            ["git", "-C", repo, "show", "-s", "--format=%ct", expected_head],
            capture_output=True, text=True, timeout=60).stdout.strip())
        if os.path.getmtime(report_path) < commit_epoch:
            problems.append("report predates the commit it claims to review — stale artefact")
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        problems.append(f"could not compare report age to commit time: {e}")

    # 8. The vendor content filter did not end the run early.
    #
    # Anchored to the vendor's actual emitted line, not to a bare substring. The substring
    # version refused a COMPLETED review of 2a1f03e: its single "hit" was this very file's
    # source, echoed into the reviewer's log because the reviewer read
    # skills/pr-release-gate/scripts/accept_verdict.py while reviewing the branch. Moving
    # this checker into the repo is what put its own detector string in front of a reader —
    # so the detector matched itself and reported a filter event that never happened.
    #
    # The real message is emitted by the CLI on its own line:
    #   ERROR: This content was flagged for possible cybersecurity risk. ...
    # Requiring the ERROR: prefix at line start distinguishes an emitted event from any
    # quotation of the phrase in reviewed source, a brief, or a commit message.
    FILTER_LINE = re.compile(
        r"^ERROR: This content was flagged for possible cybersecurity risk", re.M)
    try:
        log = open(log_path, errors="replace").read()
        hits = len(FILTER_LINE.findall(log))
        if hits:
            problems.append(f"vendor content filter fired {hits}x — aborted, not concluded")
        if not log.strip():
            problems.append("reviewer log is empty — no evidence the run executed")
    except OSError as e:
        problems.append(f"reviewer log unreadable: {e}")

    return problems


def main() -> int:
    report, log, head, repo = sys.argv[1:5]
    problems = check(report, log, head, repo)
    if problems:
        print("NOT ACTIONABLE:")
        for p in problems:
            print(f"  - {p}")
        return 1
    d = json.load(open(report))
    print(f"ACTIONABLE VERDICT: {d['verdict']} bound to {d['head_sha']}")
    for f in d.get("blocking_findings") or []:
        print(f"  [{f['severity']}] {f['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
