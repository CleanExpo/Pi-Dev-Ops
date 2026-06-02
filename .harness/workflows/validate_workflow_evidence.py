#!/usr/bin/env python3
"""Validate Pi-Dev-Ops senior-engineer workflow manifest + evidence.

Usage:
  python .harness/workflows/validate_workflow_evidence.py path/to/manifest.json path/to/evidence.md

This is deliberately stricter than a markdown presence check. It enforces the
senior-engineer Dynamic Workflow gates: connection mapping, bloat control,
verification evidence, independent review, and final state.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REQUIRED_MANIFEST_KEYS = [
    "workflow_id",
    "intent",
    "risk",
    "models",
    "budgets",
    "scope",
    "verification",
    "governance",
]
REQUIRED_EVIDENCE_SECTIONS = [
    "## Scope",
    "## Connections",
    "## Plan",
    "## Verification",
    "## Independent review",
    "## Token and bloat controls",
    "## Final state",
]
ALLOWED_FINAL_STATES = {"complete", "blocked", "rolled back"}
PLACEHOLDER_PATTERNS = [
    r"<[^>]+>",
    r"pass\s*/\s*fail",
    r"complete\s*/\s*blocked\s*/\s*rolled back",
    r"none\s*/\s*list",
    r"todo",
    r"tbd",
]


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def _section(text: str, heading: str) -> str:
    pattern = rf"^{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    if next_heading:
        rest = rest[: next_heading.start()]
    return rest.strip()


def _line_value(text: str, label: str) -> str:
    pattern = rf"^-\s*{re.escape(label)}\s*:\s*(.*?)\s*$"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def _has_placeholder(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS)


def _bullet_values(section: str, label: str) -> list[str]:
    """Read list-ish values after 'Label:' from evidence sections."""
    values: list[str] = []
    lines = section.splitlines()
    capturing = False
    for line in lines:
        stripped = line.strip()
        if re.match(rf"^{re.escape(label)}\s*:\s*$", stripped, flags=re.IGNORECASE):
            capturing = True
            continue
        if capturing:
            if re.match(r"^[A-Za-z][A-Za-z /_-]+:\s*", stripped) and not stripped.startswith(("-", "*")):
                break
            if stripped.startswith(("- ", "* ")):
                values.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("```"):
                values.append(stripped)
        else:
            inline = re.match(rf"^{re.escape(label)}\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)
            if inline:
                raw = inline.group(1).strip()
                if raw and raw.lower() not in {"none", "n/a"}:
                    values.extend([part.strip() for part in raw.split(",") if part.strip()])
    return values


def _git_changed_files(repo: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        files.append(path.replace("\\", "/"))
    return files


def _matches_any(path: str, patterns: list[str]) -> bool:
    norm = path.replace("\\", "/")
    return any(fnmatch.fnmatch(norm, pattern.replace("\\", "/")) for pattern in patterns)


def _validate_manifest(manifest: dict[str, Any]) -> str | None:
    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
    if missing:
        return f"manifest missing keys: {', '.join(missing)}"

    governance = manifest.get("governance", {})
    if governance.get("allows_secret_change"):
        return "manifest allows secret changes; requires explicit human approval"
    if governance.get("allows_destructive_migration"):
        return "manifest allows destructive migration; requires explicit human approval"

    budgets = manifest.get("budgets", {})
    for key in ("max_agents", "max_turns_per_agent", "max_wall_minutes", "max_changed_files"):
        value = budgets.get(key)
        if not isinstance(value, int) or value < 1:
            return f"budgets.{key} must be a positive integer"

    scope = manifest.get("scope", {})
    for key in ("allowed_paths", "denied_paths", "expected_change_paths"):
        if key in scope and not isinstance(scope.get(key), list):
            return f"scope.{key} must be a list"

    verification = manifest.get("verification", {})
    if verification.get("requires_independent_review") is not True:
        return "verification.requires_independent_review must be true"
    if "required_commands" not in verification or not isinstance(verification.get("required_commands"), list):
        return "verification.required_commands must be a list"

    return None


def _validate_evidence(manifest: dict[str, Any], evidence: str, evidence_path: Path, repo: Path) -> str | None:
    missing_sections = [section for section in REQUIRED_EVIDENCE_SECTIONS if section not in evidence]
    if missing_sections:
        return f"evidence missing sections: {', '.join(missing_sections)}"

    workflow_id = _line_value(evidence, "Workflow ID")
    if workflow_id != str(manifest.get("workflow_id")):
        return "evidence Workflow ID must match manifest.workflow_id"

    for heading in REQUIRED_EVIDENCE_SECTIONS:
        section = _section(evidence, heading)
        if not section:
            return f"{heading} section must not be empty"
        if _has_placeholder(section):
            return f"{heading} contains unresolved placeholder text"

    connections = _section(evidence, "## Connections")
    for required in ("Touched systems", "Data/auth path", "Existing tests or probes"):
        if required.lower() not in connections.lower():
            return f"## Connections must record {required}"

    verification_section = _section(evidence, "## Verification")
    required_commands = manifest.get("verification", {}).get("required_commands", [])
    for command in required_commands:
        if command and command not in verification_section:
            return f"verification missing required command evidence: {command}"
    if required_commands and not re.search(r"\b(PASS|passed|0 failed|exit[_ -]?code\s*[:=]\s*0)\b", verification_section, flags=re.IGNORECASE):
        return "verification must include passing command evidence"

    review = _section(evidence, "## Independent review")
    reviewer = re.search(r"^Reviewer:\s*(.+)$", review, flags=re.IGNORECASE | re.MULTILINE)
    implementer = re.search(r"^Implementer:\s*(.+)$", review, flags=re.IGNORECASE | re.MULTILINE)
    decision = re.search(r"^Decision:\s*(pass|fail)\b", review, flags=re.IGNORECASE | re.MULTILINE)
    if not reviewer or not reviewer.group(1).strip():
        return "independent review must name a reviewer"
    if not implementer or not implementer.group(1).strip():
        return "independent review must name an implementer"
    if reviewer.group(1).strip().lower() == implementer.group(1).strip().lower():
        return "independent reviewer must differ from implementer"
    if not decision or decision.group(1).lower() != "pass":
        return "independent review Decision must be pass"

    scope_section = _section(evidence, "## Scope")
    changed_files = _bullet_values(scope_section, "Actual changed files") or _git_changed_files(repo)
    max_changed_files = manifest.get("budgets", {}).get("max_changed_files", 0)
    if len(changed_files) > max_changed_files:
        return f"changed file count {len(changed_files)} exceeds budget {max_changed_files}"

    denied_patterns = manifest.get("scope", {}).get("denied_paths", [])
    denied_touched = [path for path in changed_files if _matches_any(path, denied_patterns)]
    if denied_touched:
        return f"denied paths touched: {', '.join(denied_touched)}"

    expected_patterns = manifest.get("scope", {}).get("expected_change_paths", [])
    if expected_patterns:
        unexpected = [path for path in changed_files if not _matches_any(path, expected_patterns)]
        if unexpected:
            return f"changed files outside expected_change_paths: {', '.join(unexpected)}"

    final_state = _section(evidence, "## Final state").strip().lower()
    if final_state not in ALLOWED_FINAL_STATES:
        return "final state must be exactly complete, blocked, or rolled back"
    if final_state == "complete" and not re.search(r"^Decision:\s*pass\b", review, flags=re.IGNORECASE | re.MULTILINE):
        return "complete final state requires passing independent review"

    if evidence_path.name.startswith("senior-engineer-evidence"):
        return "evidence must be a run-specific file, not the reusable template"

    return None


def _repo_from_manifest_path(manifest_path: Path) -> Path:
    """Resolve the git repo root for manifests stored anywhere under .harness.

    Previous logic assumed a fixed depth under .harness and could resolve to the
    .harness directory itself for .harness/workflows/runs/*.json. That made git
    status paths appear as ../app/... and caused false outside-scope failures.
    """
    resolved = manifest_path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == ".harness":
            return parent.parent
    return Path.cwd()


def validate_paths(manifest_path: Path, evidence_path: Path, repo: Path | None = None) -> str | None:
    repo = repo or _repo_from_manifest_path(manifest_path)

    if not manifest_path.exists():
        return f"manifest not found: {manifest_path}"
    if not evidence_path.exists():
        return f"evidence not found: {evidence_path}"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"manifest is not valid JSON: {exc}"

    manifest_error = _validate_manifest(manifest)
    if manifest_error:
        return manifest_error

    evidence = evidence_path.read_text(encoding="utf-8")
    return _validate_evidence(manifest, evidence, evidence_path, repo)


def main_for_test(manifest: str, evidence: str, repo: Path | None = None) -> int:
    return 0 if validate_paths(Path(manifest), Path(evidence), repo=repo) is None else 1


def main() -> int:
    if len(sys.argv) != 3:
        return fail("expected manifest.json and evidence.md paths")

    error = validate_paths(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    if error:
        return fail(error)

    print("PASS: workflow manifest and evidence satisfy senior-engineer gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
