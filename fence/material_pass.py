#!/usr/bin/env python3
"""material_pass.py — R4. Replace every use of 'material', don't define it.

Same method that settled R2 (production): a word that resolves through judgement
is replaced with a number, a list, or nothing. Definitions were never tried,
deliberately — defining 'material' just moves the judgement into the definition.

Buckets:
  1 THRESHOLD  a number settles it        -> founder supplies one figure per family
  2 LIST       an enumeration settles it  -> the list already exists or is cheap to build
  3 JUDGEMENT  neither works              -> the only bucket the founder rules on

Writes material-pass.csv (every occurrence, file:line, bucket, proposed replacement).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1
           else r"D:\Authority-Site\docs\constitution")
OUT = Path(__file__).parent / "material-pass.csv"

RX = re.compile(r"\bmaterial(?:ly|s)?\b", re.I)

# Ordered: first match wins. JUDGEMENT is checked first so that
# "material harm to a stakeholder" is not miscounted as a LIST because of "stakeholder".
JUDGEMENT = re.compile(
    r"\b(harm|welfare|wellbeing|trust|false|mislead|misleading|impression|"
    r"understanding|undermin\w*|dignity|reputation|reputational|uncertain\w*|"
    r"confidence|unreliab\w*|misrepresent\w*|significan\w*|importan\w*|"
    r"vulnerab\w*|ethical|moral|fair\w*|quality|judgement|judgment|"
    r"interpret\w*|drift|conflict of interest)\b", re.I)

THRESHOLD = re.compile(
    r"\b(financial|spend\w*|expenditure|cost|costs|budget|price|pricing|revenue|"
    r"resource|resources|invest\w*|commitment|commitments|payment|"
    r"time|delay|duration|period|deadline|frequency|volume|scale|size|"
    r"percentage|proportion|number|count|threshold|limit|quota)\b", re.I)

LIST = re.compile(
    r"\b(system|systems|role|roles|tool|tools|data|dataset|project|projects|"
    r"stakeholder|stakeholders|decision|decisions|exception|exceptions|"
    r"permission|permissions|authority|authorities|communication|communications|"
    r"incident|incidents|register|registers|record|records|document|documents|"
    r"asset|assets|dependency|dependencies|integration|integrations|supplier|"
    r"environment|environments|branch|branches|database|databases|host|hosts|"
    r"change|changes|action|actions|work|task|artefact|artifact|"
    r"legal|regulatory|contractual|policy|doctrine|principle)\b", re.I)

PROPOSAL = {
    "THRESHOLD": "delete the word; state the figure (e.g. 'over $X' / 'longer than N days')",
    "LIST":      "delete the word; name the set (reuse fence.json where it already exists)",
    "JUDGEMENT": "FOUNDER RULES: pick a proxy, accept a human gate, or cut the clause",
}


# 'materials', 'source/raw/reading material' are a different word entirely — the
# noun, not the qualifier. They are not in scope for R4 and are excluded, not bucketed.
NOT_THE_QUALIFIER = re.compile(
    r"\bmaterials\b|\b(source|raw|reading|reference|training|course|marketing|"
    r"promotional|written|supporting)\s+material\b", re.I)


def bucket(head: str, context: str) -> str:
    """Classify on the QUALIFIED NOUN first. The surrounding window is a fallback
    only — letting a word 90 characters away decide the bucket is how a clause about
    money gets filed under judgement."""
    for rx, name in ((JUDGEMENT, "JUDGEMENT"), (THRESHOLD, "THRESHOLD"), (LIST, "LIST")):
        if rx.search(head):
            return name
    for rx, name in ((JUDGEMENT, "JUDGEMENT"), (THRESHOLD, "THRESHOLD"), (LIST, "LIST")):
        if rx.search(context):
            return name
    return "JUDGEMENT"      # genuinely unclassifiable defaults to needing a human


def main() -> int:
    if not SRC.exists():
        print(f"source not found: {SRC}", file=sys.stderr)
        return 2
    rows, counts = [], {"THRESHOLD": 0, "LIST": 0, "JUDGEMENT": 0, "NOT-IN-SCOPE": 0}
    for f in sorted(SRC.glob("*.md")):
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in RX.finditer(line):
                lo, hi = max(0, m.start() - 90), min(len(line), m.end() + 90)
                ctx = line[lo:hi].strip()
                # the qualified noun: the 4 words immediately after
                head = " ".join(line[m.end():m.end() + 60].split()[:4])
                window = line[max(0, m.start() - 25):m.end() + 25]
                b = ("NOT-IN-SCOPE" if NOT_THE_QUALIFIER.search(window)
                     else bucket(head, ctx))
                counts[b] += 1
                rows.append({
                    "file": f.name, "line": n, "bucket": b,
                    "phrase": m.group(0), "qualified_noun": head[:60],
                    "context": re.sub(r"\s+", " ", ctx)[:200],
                    "proposed_replacement": PROPOSAL.get(b, "not the qualifier — leave alone"),
                })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    total = sum(counts.values())
    print(f"total occurrences: {total}")
    for b in ("THRESHOLD", "LIST", "JUDGEMENT"):
        print(f"  {b:<10} {counts[b]:>4}  ({counts[b]*100//max(total,1)}%)")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
