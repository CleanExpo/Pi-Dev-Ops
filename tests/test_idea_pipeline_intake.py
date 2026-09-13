"""UNI-2633 — IDEAS.md intake. No formatting demanded."""

from __future__ import annotations

from pathlib import Path

from app.server.idea_pipeline.intake import (
    append_idea,
    idea_id_for,
    parse_ideas_markdown,
    read_ideas,
)


def test_parse_plain_sentences_and_margot_prefix(tmp_path: Path) -> None:
    raw = """
# Ideas

Drop one to three sentences. No formatting needed.

---

Teach shop owners to film product videos at their own pace.

---

margot: A weekly reminder that helps a cafe owner practise one sales conversation.
"""
    ideas = parse_ideas_markdown(raw, intake_path=tmp_path / "IDEAS.md")
    assert len(ideas) == 2
    assert ideas[0].source == "phill"
    assert "shop owners" in ideas[0].text
    assert ideas[1].source == "margot"
    assert "cafe owner" in ideas[1].text
    assert ideas[0].idea_id.startswith("idea-")
    assert ideas[0].idea_id == idea_id_for(ideas[0].text)


def test_blank_line_blocks_need_no_separators(tmp_path: Path) -> None:
    raw = (
        "Help a salon owner grow with a short self-paced lesson.\n\n"
        "Something else that teaches a shop owner video and audio lessons."
    )
    ideas = parse_ideas_markdown(raw, intake_path=tmp_path / "IDEAS.md")
    assert len(ideas) == 2


def test_append_idea_writes_margot_line(tmp_path: Path) -> None:
    path = tmp_path / "IDEAS.md"
    first = append_idea(path, "Teach owners a short self-paced growth lesson.", source="phill")
    second = append_idea(
        path,
        "A cafe owner gets a weekly sales practice reminder.",
        source="margot",
    )
    text = path.read_text(encoding="utf-8")
    assert "margot:" in text
    assert first.source == "phill"
    assert second.source == "margot"
    loaded = read_ideas(path)
    assert {row.idea_id for row in loaded} == {first.idea_id, second.idea_id}


def test_empty_or_missing_intake_is_empty(tmp_path: Path) -> None:
    missing = tmp_path / "IDEAS.md"
    assert read_ideas(missing) == []
    missing.write_text("# Ideas\n\nDrop one to three sentences.\n", encoding="utf-8")
    assert read_ideas(missing) == []
