#!/usr/bin/env python3
"""Decide whether a challenge report is admissible. Exit 0 = admissible.

    validate_report.py <report.json>

WHY IT IS SHAPED LIKE THIS. This is the pass boundary of the whole challenge loop: what
gets past here becomes a clearance. Four spellings of it have now been defeated in
independent review, each one a check that LOOKED like the real thing:

    json.load() alone            `{}` decodes, and anchor.py reads absent
                                 blocking_findings as zero findings
    required-key presence        all six keys present, every value wrong
    partial JSON-Schema walk     unsupported keyword under an unvisited `items`
    ...the same walk, fixed      schema-valued additionalProperties, and keyword
                                 values that were themselves malformed

The pattern is the lesson, not the individual holes: a validator that INTERPRETS a
schema is an open surface, and an open surface loses to an adversary every time. Each
repair closed one hole and opened the next.

So this no longer interprets anything. The admissible shape is written out here, in
full, as closed code — an allowlist, not a search for bad things. There is no traversal
to have a gap in and no keyword that can be silently skipped, because no keyword is
read at all. challenge-schema.json remains the contract handed to the challenger via
--output-schema; tests/test_scripts.py asserts this file and that one still describe the
same report, so the two cannot drift apart unnoticed.

Detail goes to stderr for the caller to log. The caller must NEVER interpolate it into
its own output: it quotes key names the challenger chose.
"""

from __future__ import annotations

import json
import sys

TOP = {"schema", "verdict", "blocking_findings", "advisory_findings",
       "independent_research", "unchallenged"}
FINDING = {"severity", "claim", "defect", "evidence", "fix"}
SEVERITIES = {"blocking_findings": {"P0", "P1"}, "advisory_findings": {"P2"}}


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)   # `true` is not an integer


def check_findings(value, name: str, errs: list[str]) -> None:
    if not isinstance(value, list):
        errs.append(f"{name}: must be an array")
        return
    for i, f in enumerate(value):
        at = f"{name}[{i}]"
        if not isinstance(f, dict):
            errs.append(f"{at}: must be an object")
            continue
        if set(f) != FINDING:
            errs.append(f"{at}: fields must be exactly {sorted(FINDING)}")
            continue
        if f["severity"] not in SEVERITIES[name]:
            errs.append(f"{at}.severity: must be one of {sorted(SEVERITIES[name])}")
        for k in FINDING - {"severity"}:
            if not isinstance(f[k], str) or not f[k].strip():
                errs.append(f"{at}.{k}: must be a non-empty string")


def check(report) -> list[str]:
    if not isinstance(report, dict):
        return ["report: must be a JSON object"]

    errs: list[str] = []
    for k in sorted(TOP - set(report)):
        errs.append(f"{k}: required key missing")
    for k in sorted(set(report) - TOP):
        errs.append(f"{k!r}: unexpected key")
    if errs:
        return errs

    if not is_int(report["schema"]):
        errs.append("schema: must be an integer")
    if report["verdict"] not in ("PASS", "FAIL"):
        errs.append("verdict: must be PASS or FAIL")
    for name in SEVERITIES:
        check_findings(report[name], name, errs)
    for name in ("independent_research", "unchallenged"):
        v = report[name]
        if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
            errs.append(f"{name}: must be an array of strings")
    return errs


def main() -> int:
    try:
        # encoding is load-bearing: without it Windows decodes as cp1252 and any
        # smart quote the challenger writes raises UnicodeDecodeError, which the
        # caller classifies as NO_VERDICT — a real FAIL verdict with findings was
        # discarded as an invalid report on 2026-08-14 for exactly this reason.
        with open(sys.argv[1], encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, IndexError) as e:
        print(f"unreadable: {e}", file=sys.stderr)
        return 2

    errs = check(report)
    if errs:
        print("; ".join(errs), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
