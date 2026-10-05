"""The manifest must export the description the runtime loader reads, not its YAML quoting."""
from swarm.agentskills_manifest import _parse_frontmatter


def test_a_quoted_description_exports_without_its_quotes():
    fields, body = _parse_frontmatter('---\nname: demo\ndescription: "Plan: then build `x`."\n---\n# Body\n')
    assert fields["description"] == "Plan: then build `x`."
    assert fields["name"] == "demo"
    assert body.strip() == "# Body"


def test_a_folded_description_exports_as_text():
    fields, _ = _parse_frontmatter("---\nname: demo\ndescription: >\n  Runs the demo\n  end to end.\n---\nx\n")
    assert fields["description"].strip() == "Runs the demo end to end."


def test_broken_yaml_falls_back_to_the_line_reader():
    fields, _ = _parse_frontmatter("---\nname: demo\ndescription: a: b: c\n---\nx\n")
    assert fields["name"] == "demo"
    assert fields["description"] == "a: b: c"
