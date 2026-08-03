#!/usr/bin/env python3
"""material_delete_pass.py — R4 default: delete the qualifier.

Drop 'material' / 'materially' and read the clause back. Almost always it gets
shorter, plainer and STRICTER, which is the point: "escalate where a stakeholder
may be harmed" binds harder than "may be materially harmed", and needs no ruling.

The only interesting output is the residue: clauses that genuinely break.

A clause BREAKS when deletion makes the rule non-actionable, which happens in
exactly two ways:

  1. HEAD NOUN — 'material' is the noun, not the qualifier ("source material",
     "materials"). Deleting it removes the subject of the sentence.

  2. ALWAYS-TRUE — the qualified thing is a universal property of all work
     (risk, uncertainty, change, difference, cost). Every action carries some
     risk, so "escalate where there is risk" fires on everything and therefore
     gates nothing. The word was carrying a threshold, and deleting it without
     supplying a number replaces a vague gate with a useless one.

Everything else: delete it. No ruling required.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

CSV_IN = Path(r"D:\Pi-Dev-Ops\fence\material-pass.csv")
OUT = Path(r"D:\Pi-Dev-Ops\fence\material-delete-pass.csv")

# Universal properties: every piece of work has some. Removing the qualifier
# makes the clause fire on everything, i.e. gate nothing.
ALWAYS_TRUE = re.compile(
    r"\b(risk|risks|uncertaint\w*|change|changes|difference|differences|"
    r"cost|costs|impact|effect|significance|importance|amount|extent|degree|"
    r"level|scale|magnitude)\b", re.I)

HEAD_NOUN = re.compile(
    r"\bmaterials\b|\b(source|raw|reading|reference|training|course|marketing|"
    r"promotional|written|supporting)\s+material\b", re.I)


VOWEL = re.compile(r"\b([Aa])\s+(?=[aeiouAEIOU])")


def delete(text: str) -> str:
    # predicate forms first: "remains material," / "becomes material." / "is material"
    out = re.sub(r"\s+(is|are|was|were|remains?|becomes?|seems?|appears?)\s+material\b",
                 "", text, flags=re.I)
    # attributive forms: "materially harmed", "material risk"
    out = re.sub(r"\bmaterially\s+", "", out, flags=re.I)
    out = re.sub(r"\bmaterial\s+", "", out, flags=re.I)
    # bare trailing use before punctuation: "if the effect is material."
    out = re.sub(r"\bmaterial\b(?=\s*[,.;:)])", "", out, flags=re.I)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"\s+", " ", out)
    # deleting the qualifier can strand the wrong article: "a appointment"
    out = VOWEL.sub(lambda m: ("An " if m.group(1) == "A" else "an ") + "", out)
    return out.strip()


PREDICATE = re.compile(
    r"\b(is|are|was|were|remains?|becomes?|seems?|appears?)\s+material\b", re.I)


def verdict(ctx: str, head: str) -> tuple[str, str]:
    if HEAD_NOUN.search(ctx):
        return "BREAKS", "'material' is the noun here, not a qualifier"
    if PREDICATE.search(ctx):
        return "BREAKS", ("used as the predicate ('is material') — deleting it removes "
                          "the verb and leaves no sentence")
    first = " ".join(head.split()[:2])
    if ALWAYS_TRUE.search(first):
        return "BREAKS", ("qualifies a universal property — without a number the rule "
                          "fires on everything and gates nothing")
    return "DELETE", "reads plainer and stricter without it"


def main() -> int:
    if not CSV_IN.exists():
        print("run material_pass.py first", file=sys.stderr)
        return 2
    rows = list(csv.DictReader(CSV_IN.open(encoding="utf-8")))
    target = [r for r in rows if r["bucket"] == "JUDGEMENT"]

    out, breaks = [], []
    for r in target:
        v, why = verdict(r["context"], r["qualified_noun"])
        rec = {"file": r["file"], "line": r["line"], "verdict": v, "why": why,
               "before": r["context"][:170], "after": delete(r["context"])[:170]}
        out.append(rec)
        if v == "BREAKS":
            breaks.append(rec)

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    print(f"bucket-3 clauses examined : {len(target)}")
    print(f"DELETE the qualifier      : {len(out) - len(breaks)}")
    print(f"genuinely BREAK           : {len(breaks)}")
    seen = {}
    for b in breaks:
        k = re.sub(r"\s+", " ", b["before"])[:70]
        seen.setdefault(k, b)
    print(f"distinct broken clauses   : {len(seen)}")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
