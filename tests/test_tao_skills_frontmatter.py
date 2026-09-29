"""The TAO skill loader must read YAML frontmatter as YAML.

A block-scalar description (``description: >``) used to reach generator prompts as the
single character ">", because the loader split frontmatter one line at a time.
"""
from pathlib import Path

from src.tao.skills import _parse_frontmatter


def test_folded_description_loads_as_text():
    meta, body = _parse_frontmatter(
        "---\nname: demo\ndescription: >\n  Runs the demo\n  end to end.\nautomation: manual\n---\n# Body\n"
    )
    assert meta["description"] == "Runs the demo end to end.\n"
    assert meta["automation"] == "manual"
    assert body == "# Body"


def test_quoted_description_loses_its_quotes():
    meta, _ = _parse_frontmatter('---\nname: demo\ndescription: "Plan: then build."\n---\nx\n')
    assert meta["description"] == "Plan: then build."


def test_every_skill_description_loads_in_full():
    """YAML must not cut a real description short (a " #" starts a comment)."""
    root = Path(__file__).resolve().parents[1] / "skills"
    cut = []
    for path in sorted(root.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        line = next((l for l in text.split("\n---", 1)[0].splitlines() if l.startswith("description:")), "")
        raw = line.split(":", 1)[1].strip() if line else ""
        if raw in ("", ">", "|", ">-", "|-"):
            continue
        meta, _ = _parse_frontmatter(text)
        if str(meta.get("description", "")) != raw.strip('"'):
            cut.append(path.parent.name)
    assert cut == []


def test_invalid_yaml_still_loads_line_by_line():
    meta, body = _parse_frontmatter("---\nname: demo\ndescription: Plan: then build.\n---\nx\n")
    assert meta == {"name": "demo", "description": "Plan: then build."}
    assert body == "x"
