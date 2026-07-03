"""tests/test_draft_skill_diff.py — scoped-diff drafter prompt + draft-file writer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.draft_skill_diff import build_dispatch_prompt, write_draft  # noqa: E402


def _lessons():
    return [
        {
            "ts": "2026-07-01T00:00:00Z",
            "source": "linear-task-processor",
            "applies_to_skill": "skill-authoring-standard",
            "lesson": "The line-count cap doesn't say whether frontmatter counts.",
            "severity": "warn",
        },
        {
            "ts": "2026-07-02T00:00:00Z",
            "source": "pr-manager",
            "applies_to_skill": "skill-authoring-standard",
            "lesson": "Two reviewers disagreed on whether frontmatter counts toward the 200-line cap.",
            "severity": "warn",
        },
        {
            "ts": "2026-07-03T00:00:00Z",
            "source": "orchestrator-reviewer",
            "applies_to_skill": "skill-authoring-standard",
            "lesson": "Same frontmatter/line-count ambiguity caused a third round-trip.",
            "severity": "error",
        },
    ]


def test_build_dispatch_prompt_includes_skill_name_and_path(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("# skill-authoring-standard\n\ncontent\n")
    prompt = build_dispatch_prompt("skill-authoring-standard", skill_md, _lessons())
    assert "skill-authoring-standard" in prompt
    assert str(skill_md) in prompt


def test_build_dispatch_prompt_includes_all_lesson_text(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("# skill-authoring-standard\n\ncontent\n")
    prompt = build_dispatch_prompt("skill-authoring-standard", skill_md, _lessons())
    for lesson in _lessons():
        assert lesson["lesson"] in prompt


def test_build_dispatch_prompt_states_append_only_constraint(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("# skill-authoring-standard\n\ncontent\n")
    prompt = build_dispatch_prompt("skill-authoring-standard", skill_md, _lessons())
    assert "append-only" in prompt.lower() or "single, scoped" in prompt.lower()


def test_write_draft_creates_file_with_diff_content(tmp_path):
    diff_text = "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1,1 +1,2 @@\n # skill\n+new line\n"
    out_dir = tmp_path / "drafts"
    path = write_draft("skill-authoring-standard", diff_text, output_dir=out_dir)
    assert path.exists()
    assert path.read_text() == diff_text
    assert path.parent == out_dir


def test_write_draft_filename_includes_skill_name(tmp_path):
    path = write_draft("agent-expert", "diff content", output_dir=tmp_path)
    assert "agent-expert" in path.name
