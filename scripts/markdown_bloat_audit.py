#!/usr/bin/env python3
"""Score markdown bloat and write safe compression audits."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".harness"}


def _recommendation(rel: str, line_count: int) -> str:
    if rel.startswith("docs/superpowers/plans/"):
        return "archive_compress"
    if rel.startswith("skills/") and rel.endswith("/SKILL.md") and line_count > 170:
        return "split_skill_references"
    if rel.endswith("CLAUDE.md") and line_count > 220:
        return "extract_references_before_trim"
    return "review_trim"


def _score(rel: str, text: str) -> tuple[int, list[str]]:
    lines = text.splitlines()
    lower = text.lower()
    score = 0
    reasons: list[str] = []
    if len(lines) > 220:
        score += len(lines) - 220
        reasons.append(f"{len(lines)} lines")
    if rel.startswith("docs/superpowers/plans/"):
        score += 250
        reasons.append("historic plan doc")
    if rel.startswith("skills/") and rel.endswith("/SKILL.md") and len(lines) > 170:
        score += 100
        reasons.append("oversized live skill")
    if lower.count("phase") > 20 or lower.count("todo") > 8:
        score += 40
        reasons.append("planning sprawl")
    if "not logged in" in lower or "please run /login" in lower:
        score += 80
        reasons.append("generated auth noise")
    return score, reasons


def audit_markdown(repo_root: str | Path, top: int = 40) -> list[dict[str, Any]]:
    root = Path(repo_root)
    results: list[dict[str, Any]] = []
    for path in root.rglob("*.md"):
        rel_path = path.relative_to(root)
        if any(part in _SKIP or part.startswith(".venv") for part in rel_path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(rel_path)
        score, reasons = _score(rel, text)
        if score <= 0:
            continue
        line_count = len(text.splitlines())
        results.append({
            "path": rel,
            "lines": line_count,
            "score": score,
            "reasons": reasons,
            "recommendation": _recommendation(rel, line_count),
        })
    return sorted(results, key=lambda item: (-int(item["score"]), str(item["path"])))[:top]


def write_audit(output_path: str | Path, report: list[dict[str, Any]]) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Markdown bloat audit", "", "| Path | Lines | Score | Recommendation | Reasons |", "|---|---:|---:|---|---|"]
    for item in report:
        lines.append(
            f"| `{item['path']}` | {item['lines']} | {item['score']} | {item['recommendation']} | {', '.join(item['reasons'])} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score markdown files for bloat/noise.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--output", default=".harness/audits/markdown-bloat-latest.md")
    args = parser.parse_args(argv)
    report = audit_markdown(args.repo_root, top=args.top)
    write_audit(Path(args.repo_root) / args.output, report)
    print(f"wrote {args.output} ({len(report)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
