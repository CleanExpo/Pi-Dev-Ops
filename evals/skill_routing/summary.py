"""Markdown table of every skill-routing report in a folder, for the GitHub job summary.

usage: python -m evals.skill_routing.summary <reports-dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

COLS = ("cases", "top1_accuracy", "shortlist_recall", "no_match_precision", "mean_skill_tokens")


def rows(report: dict) -> list[str]:
    out = []
    for mode in ("table", "lexical", "jev"):
        m = report.get(mode)
        if isinstance(m, dict):
            extra = f"${m['usd']} · p95 {m.get('p95_s')}s · errors {m.get('errors')}" if "usd" in m else ""
            out.append(f"| {report['split']} | k={report['k']} | {mode} | " + " | ".join(str(m[c]) for c in COLS) + f" | {extra} |")
        else:
            out.append(f"| {report['split']} | k={report['k']} | {mode} | {m} |")
    return out


def main() -> int:
    folder = Path(sys.argv[1])
    print("## Skill routing\n\n| split | shortlist | mode | cases | top-1 | shortlist recall | no-match precision | skill tokens | Jev cost |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path in sorted(folder.glob("*.json")):
        for line in rows(json.loads(path.read_text("utf-8"))):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
