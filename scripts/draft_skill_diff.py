"""
draft_skill_diff.py — Scoped-diff drafter for skill self-improvement (RA-continuous-moa §6.3)

Given a flagged skill name + its grouped lessons (from scan_skill_lessons.py),
builds the exact dispatch prompt for an LLM agent to draft a single, scoped,
append-only diff to that skill's SKILL.md, and writes the resulting diff to
.harness/skill-self-update-drafts/.

This module does NOT call the LLM itself — build_dispatch_prompt() returns the
prompt text; the orchestrator (skill_self_update.py) hands it to the Agent tool
(subagent_type: general-purpose) and passes the returned diff text to write_draft().
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_DRAFTS_DIR = _ROOT / ".harness" / "skill-self-update-drafts"

DISPATCH_PROMPT_TEMPLATE = """You are drafting a single, scoped patch to an existing Claude Code skill file because the skill's own process or instructions have been flagged as a recurring source of confusion.

Skill name: {skill_name}
Skill file (read this in full before drafting anything): {skill_md_path}

The following {lesson_count} lessons were logged against this skill's process within the last 30 days (each is a real mistake or point of confusion an agent hit while following this skill's instructions):

{lesson_block}

Your task:
1. Read the skill file at {skill_md_path} in full.
2. Identify the ONE existing section most relevant to these lessons (e.g. an existing gate, rule list, or step). Do not invent a new top-level section unless no existing section fits.
3. Draft a single, scoped, append-only change — typically one new bullet or one clarifying sentence added to that existing section. Do NOT rewrite, reorder, or delete any existing content. Do NOT touch YAML frontmatter unless a lesson is specifically about frontmatter being wrong.
4. Keep the addition as short as the lessons justify — usually 1-3 lines. This skill file is governed by skill-authoring-standard's review checklist, which caps SKILL.md at 200 lines total and penalises duplication, so do not restate content that already exists elsewhere in the file.
5. Output ONLY a unified diff (git diff format, `--- a/{skill_md_relpath}` / `+++ b/{skill_md_relpath}` headers, `@@` hunk markers) that applies cleanly with `git apply`. No prose before or after the diff. No markdown code fences around the diff.

If, after reading the file, you determine the lessons do not justify any change (e.g. the file already covers this, or the lessons are too vague to act on), output exactly the line `NO_CHANGE_JUSTIFIED` and nothing else — do not force a diff.
"""


def build_dispatch_prompt(skill_name: str, skill_md_path: Path, lessons: list[dict]) -> str:
    lesson_lines = []
    for entry in lessons:
        severity = entry.get("severity", "info")
        source = entry.get("source", "unknown")
        ts = entry.get("ts", "unknown")
        text = entry.get("lesson", "")
        lesson_lines.append(f"- [{severity}, from {source}, {ts}] {text}")
    lesson_block = "\n".join(lesson_lines)

    try:
        skill_md_relpath = skill_md_path.relative_to(_ROOT).as_posix()
    except ValueError:
        skill_md_relpath = skill_md_path.as_posix()

    return DISPATCH_PROMPT_TEMPLATE.format(
        skill_name=skill_name,
        skill_md_path=str(skill_md_path),
        skill_md_relpath=skill_md_relpath,
        lesson_count=len(lessons),
        lesson_block=lesson_block,
    )


def write_draft(skill_name: str, diff_text: str, output_dir: Path = _DRAFTS_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = output_dir / f"{skill_name}-{date_str}.diff"
    path.write_text(diff_text)
    return path
