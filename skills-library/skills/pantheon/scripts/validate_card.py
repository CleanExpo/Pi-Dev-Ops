#!/usr/bin/env python3
"""Seat-card validator — a card without graded citations refuses to seat.

usage: validate_card.py <card.md>   (exit 0 seat, exit 1 refuse)
Rules: ≥1 attested position with [source: <url>, grade: <A-F><1-6>...]; any quoted
string in a position must sit on a line carrying a source tag; grades worse than C3
cannot attest (extrapolation ledger instead).
"""
import re, sys

TAG = re.compile(r"\[source:\s*(\S+?)\s*,\s*grade:\s*([A-F])([1-6])", re.I)

def main():
    if len(sys.argv) != 2:
        print("usage: validate_card.py <card.md>"); return 2
    txt = open(sys.argv[1], errors="replace").read()
    m = re.search(r"## Attested positions(.*?)(\n## |\Z)", txt, re.S)
    if not m:
        print("REFUSED: no 'Attested positions' section"); return 1
    section = m.group(1)
    problems, attested = [], 0
    for line in section.splitlines():
        if not re.match(r"\s*\d+\.", line):
            continue
        tags = TAG.findall(line)
        if not tags:
            problems.append(f"position without source tag: {line.strip()[:80]}")
            continue
        rel, cred = tags[0][1].upper(), int(tags[0][2])
        if rel > "C" or cred > 3:
            problems.append(f"grade {rel}{cred} too weak to attest (worse than C3): {line.strip()[:60]}")
        else:
            attested += 1
        if ('"' in line or '“' in line) and not tags:
            problems.append(f"quote without citation: {line.strip()[:60]}")
    if attested == 0:
        problems.append("no attested position with a graded citation of C3 or better")
    if problems:
        print("REFUSED to seat card:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"SEATED: {attested} attested position(s) with graded citations")
    return 0

if __name__ == "__main__":
    sys.exit(main())
