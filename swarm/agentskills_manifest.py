"""
swarm/agentskills_manifest.py — RA-1839: agentskills.io v1 manifest exporter.

Walks Pi-Dev-Ops/skills/, normalises every SKILL.md frontmatter +
extracts dependencies + safety flags from the body, writes
agentskills.json + agentskills.yaml at repo root.

Closes RA-1838 SWARM-009 (Hermes Path C — open question #5 from the
original brief).

Usage:
    python -m swarm.agentskills_manifest

Versioning rules (manifest.package.version):
  * skill added → MINOR bump
  * skill removed → MAJOR bump
  * SKILL.md content changed (sha256 diff) → PATCH bump
  * first run → 0.1.0

Idempotency: re-running with no changes is a no-op (no version bump,
no history append).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.agentskills_manifest")

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
HISTORY_FILE = REPO_ROOT / ".harness" / "agentskills_history.jsonl"
OVERRIDES_FILE = REPO_ROOT / ".harness" / "agentskills_overrides.yaml"
JSON_OUT = REPO_ROOT / "agentskills.json"
YAML_OUT = REPO_ROOT / "agentskills.yaml"
SCHEMA_OUT = REPO_ROOT / ".harness" / "agentskills_v1.schema.json"

PACKAGE_NAME = "pi-ceo-skills"
PACKAGE_SOURCE = "github.com/CleanExpo/Pi-Dev-Ops"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_TOOL_REF_RE = re.compile(r"`(mcp\.[a-z0-9_-]+\.[a-z0-9_-]+)`")
_SKILL_REF_RE = re.compile(r"`(skill\.[a-z0-9_-]+)`")
_KILL_SWITCH_RE = re.compile(r"\b(TAO_SWARM_ENABLED|kill[- ]switch)\b", re.IGNORECASE)
_HITL_RE = re.compile(r"\b(telegram-draft-for-review|review chat|HITL)\b", re.IGNORECASE)
_PII_REDACTS_RE = re.compile(r"\bpii-redactor\b", re.IGNORECASE)


@dataclass
class SkillEntry:
    id: str
    description: str
    owner_role: str
    status: str
    path: str
    sha256: str
    dependencies: dict[str, list[str]] = field(default_factory=lambda: {"tools": [], "skills": []})
    safety: dict[str, Any] = field(default_factory=dict)
    inferred: bool = False
    low_confidence: bool = False


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Naive YAML-ish frontmatter parser. Returns (fields, body)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    fm_text, body = m.group(1), m.group(2)
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
    return fields, body


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_dependencies(body: str) -> dict[str, list[str]]:
    tools = sorted(set(_TOOL_REF_RE.findall(body)))
    skills = sorted(set(_SKILL_REF_RE.findall(body)))
    return {"tools": tools, "skills": skills}


def _extract_safety(body: str) -> dict[str, Any]:
    return {
        "requires_kill_switch": bool(_KILL_SWITCH_RE.search(body)),
        "requires_hitl_gate": bool(_HITL_RE.search(body)),
        "pii_handling": "redacts" if _PII_REDACTS_RE.search(body) else "pass-through",
    }


def _scan_skill(skill_dir: Path) -> SkillEntry | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    content = skill_md.read_text(encoding="utf-8")
    fields, body = _parse_frontmatter(content)
    name = fields.get("name") or skill_dir.name
    deps = _extract_dependencies(body)
    safety = _extract_safety(body)
    inferred = not deps["tools"] and not deps["skills"] and len(body) > 100 * 5

    return SkillEntry(
        id=name,
        description=fields.get("description", ""),
        owner_role=fields.get("owner_role", "(unset)"),
        status=fields.get("status", "(unset)"),
        path=str(skill_md.relative_to(REPO_ROOT)),
        sha256=_sha256(content),
        dependencies=deps,
        safety=safety,
        inferred=inferred,
        low_confidence=inferred,
    )


def _entry_to_dict(e: SkillEntry) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": e.id,
        "description": e.description,
        "owner_role": e.owner_role,
        "status": e.status,
        "path": e.path,
        "sha256": e.sha256,
        "dependencies": e.dependencies,
        "safety": e.safety,
    }
    if e.inferred:
        out["inferred"] = True
    if e.low_confidence:
        out["low_confidence"] = True
    return out


def _scan_registry() -> list[SkillEntry]:
    if not SKILLS_DIR.exists():
        return []
    entries: list[SkillEntry] = []
    for child in sorted(SKILLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("__"):
            continue
        e = _scan_skill(child)
        if e:
            entries.append(e)
    return entries


def _load_previous_manifest() -> dict[str, Any] | None:
    if not JSON_OUT.exists():
        return None
    try:
        return json.loads(JSON_OUT.read_text())
    except Exception as exc:
        log.warning("previous manifest unreadable: %s", exc)
        return None


def _bump_version(prev: dict[str, Any] | None,
                 prev_skills_by_id: dict[str, dict[str, Any]],
                 new_skills_by_id: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Return (new_version, bump_reason)."""
    if prev is None:
        return "0.1.0", "first_run"

    prev_version = prev.get("package", {}).get("version", "0.1.0")
    parts = [int(x) for x in prev_version.split(".")]
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[0], parts[1], parts[2]

    added = set(new_skills_by_id) - set(prev_skills_by_id)
    removed = set(prev_skills_by_id) - set(new_skills_by_id)
    common = set(prev_skills_by_id) & set(new_skills_by_id)
    content_changed = any(
        prev_skills_by_id[k]["sha256"] != new_skills_by_id[k]["sha256"]
        for k in common
    )

    if removed:
        return f"{major + 1}.0.0", f"removed_{len(removed)}"
    if added:
        return f"{major}.{minor + 1}.0", f"added_{len(added)}"
    if content_changed:
        return f"{major}.{minor}.{patch + 1}", "content_changed"
    return prev_version, "no_change"


def _write_yaml(obj: Any, path: Path) -> None:
    """Write YAML without depending on PyYAML. Hand-rolled, sufficient for our schema."""
    def emit(o: Any, indent: int = 0) -> str:
        pad = "  " * indent
        if isinstance(o, dict):
            if not o:
                return "{}"
            lines = []
            for k, v in o.items():
                if isinstance(v, (dict, list)) and v:
                    lines.append(f"{pad}{k}:")
                    lines.append(emit(v, indent + 1))
                else:
                    lines.append(f"{pad}{k}: {_yaml_scalar(v)}")
            return "\n".join(lines)
        if isinstance(o, list):
            if not o:
                return "[]"
            lines = []
            for item in o:
                if isinstance(item, (dict, list)):
                    body = emit(item, indent + 1)
                    first, _, rest = body.partition("\n")
                    lines.append(f"{pad}- {first.strip()}")
                    if rest:
                        lines.append(rest)
                else:
                    lines.append(f"{pad}- {_yaml_scalar(item)}")
            return "\n".join(lines)
        return f"{pad}{_yaml_scalar(o)}"

    path.write_text(emit(obj) + "\n", encoding="utf-8")


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(ch in s for ch in ":#\n\"'") or s in ("true", "false", "null", ""):
        return json.dumps(s)
    return s


def _vendored_schema() -> dict[str, Any]:
    """Minimal agentskills.io v1 schema. Vendored offline copy."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://agentskills.io/schemas/v1/manifest.schema.json",
        "title": "agentskills.io Manifest v1",
        "type": "object",
        "required": ["manifest_version", "package", "skills"],
        "properties": {
            "manifest_version": {"const": 1},
            "package": {
                "type": "object",
                "required": ["name", "version", "generated_at", "source"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                    "generated_at": {"type": "string", "format": "date-time"},
                    "source": {"type": "string"},
                },
            },
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "description", "owner_role", "status", "path", "sha256"],
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "owner_role": {"type": "string"},
                        "status": {"type": "string"},
                        "path": {"type": "string"},
                        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "dependencies": {
                            "type": "object",
                            "properties": {
                                "tools": {"type": "array", "items": {"type": "string"}},
                                "skills": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                        "safety": {
                            "type": "object",
                            "properties": {
                                "requires_kill_switch": {"type": "boolean"},
                                "requires_hitl_gate": {"type": "boolean"},
                                "pii_handling": {"enum": ["pass-through", "redacts", "tokenizes"]},
                            },
                        },
                        "inferred": {"type": "boolean"},
                        "low_confidence": {"type": "boolean"},
                    },
                },
            },
        },
    }


def export() -> dict[str, Any]:
    """Walk skills/, build manifest, write JSON + YAML, append history. Return manifest dict."""
    # Ensure schema is vendored
    SCHEMA_OUT.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_OUT.write_text(json.dumps(_vendored_schema(), indent=2))

    entries = _scan_registry()
    new_skills = [_entry_to_dict(e) for e in entries]
    new_by_id = {s["id"]: s for s in new_skills}

    prev = _load_previous_manifest()
    prev_by_id = {s["id"]: s for s in (prev.get("skills", []) if prev else [])}

    version, reason = _bump_version(prev, prev_by_id, new_by_id)

    manifest = {
        "manifest_version": 1,
        "package": {
            "name": PACKAGE_NAME,
            "version": version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": PACKAGE_SOURCE,
        },
        "skills": sorted(new_skills, key=lambda s: s["id"]),
    }

    JSON_OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_yaml(manifest, YAML_OUT)

    if reason != "no_change":
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": manifest["package"]["generated_at"],
                "version": version,
                "reason": reason,
                "skill_count": len(new_skills),
            }) + "\n")

    return manifest


if __name__ == "__main__":
    m = export()
    print(f"Wrote {JSON_OUT.relative_to(REPO_ROOT)} (version {m['package']['version']})")
    print(f"Wrote {YAML_OUT.relative_to(REPO_ROOT)}")
    print(f"Skills exported: {len(m['skills'])}")
    print(f"Schema vendored at {SCHEMA_OUT.relative_to(REPO_ROOT)}")
    sys.exit(0)
