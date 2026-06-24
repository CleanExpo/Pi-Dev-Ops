#!/usr/bin/env python3
"""Build a safe split packet for oversized SKILL.md files."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _frontmatter_and_body(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---\n", 3)
    if end == -1:
        return "", text
    return text[: end + 5], text[end + 5 :].lstrip()


def _skill_name(frontmatter: str, skill_path: Path) -> str:
    match = re.search(r"^name:\s*([^\n]+)", frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else skill_path.parent.name


def build_split_packet(skill_path: str | Path) -> dict[str, str]:
    path = Path(skill_path)
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _frontmatter_and_body(text)
    name = _skill_name(frontmatter, path)
    headings = list(re.finditer(r"^##\s+", body, flags=re.MULTILINE))
    if len(headings) >= 2:
        keep_end = headings[1].start()
    else:
        keep_end = min(len(body), 1200)
    kept = body[:keep_end].rstrip()
    extracted = body[keep_end:].strip() or body.strip()
    reference_path = "references/extracted-detail.md"
    router = (
        f"{frontmatter}\n"
        f"{kept}\n\n"
        "## Long-form detail\n"
        f"Detailed doctrine/procedure was extracted to `{reference_path}`. Load it only when the task requires the full playbook.\n"
    ).strip() + "\n"
    reference = f"# Extracted detail for {name}\n\n{extracted}\n"
    return {
        "skill": name,
        "source_path": str(path),
        "reference_path": reference_path,
        "router_markdown": router,
        "reference_markdown": reference,
        "action": "proposal_only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a proposal packet to split a large SKILL.md.")
    parser.add_argument("skill_path")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    packet = build_split_packet(args.skill_path)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(packet), encoding="utf-8")
    else:
        print(packet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
