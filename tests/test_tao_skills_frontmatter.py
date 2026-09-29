"""The TAO skill loader must read YAML frontmatter as YAML.

A block-scalar description (``description: >``) used to reach generator prompts as the
single character ">", because the loader split frontmatter one line at a time.
"""
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


def test_invalid_yaml_still_loads_line_by_line():
    meta, body = _parse_frontmatter("---\nname: demo\ndescription: Plan: then build.\n---\nx\n")
    assert meta == {"name": "demo", "description": "Plan: then build."}
    assert body == "x"
