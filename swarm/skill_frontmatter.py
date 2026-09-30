"""SKILL.md frontmatter for the agentskills manifest.

Every field comes from the line reader the manifest has always used, so other fields keep
their exported form. The description alone is taken from real YAML when the block parses,
as the runtime loader (src/tao/skills.py) does, so a quoted description exports without its
quotes and the manifest matches what Mission Control loads.
"""
from __future__ import annotations

import re

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Returns (fields, body)."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    fm_text, body = m.group(1), m.group(2)
    fields = _line_fields(fm_text)
    try:
        import yaml

        data = yaml.safe_load(fm_text)
    except Exception:
        data = None
    if isinstance(data, dict) and isinstance(data.get("description"), str):
        fields["description"] = data["description"]
    return fields, body


def _line_fields(fm_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in fm_text.splitlines():
        if not line.strip():
            continue
        if line.startswith(" ") and current_key:
            fields[current_key] = (fields[current_key] + " " + line.strip()).strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            current_key = k.strip()
            fields[current_key] = v.strip()
    return fields
