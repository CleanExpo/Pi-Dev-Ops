"""workspace_context.py — compose the CLAUDE.md planted into a generated workspace.

A generated session used to receive a three-line containment stub: "this is an isolated
workspace, do not walk upward". True, necessary, and completely silent about what is being
built or for whom. Every session therefore started in the state a vague ticket produces —
the generator had to infer the product, the buyer and the quality bar from the diff.

Pi-CEO already holds those facts. `config/harness/projects.json` carries the repo, stack,
deployments and Linear routing for each portfolio project, and seven of them additionally
declare a `business_charter`. Nothing was passing any of it to the workspace.

Two rules shape this module:

  * The containment guard stays first and unconditional. It is load-bearing — without it
    Claude Code walks up into an ancestor repo's CLAUDE.md (RA-1169-1178).
  * Nothing is invented. Only registry facts and charter text are emitted. Where context
    is declared but unresolvable, the file SAYS SO rather than omitting the section: a
    generator that can see "charter declared but missing" can flag it, while one handed a
    silently shorter file cannot tell that from a project having no charter at all.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import config_loader

log = logging.getLogger("pi-ceo.workspace_context")

_GUARD = (
    "# Scoped Pi-CEO workspace\n\n"
    "This is an isolated autonomous workspace. Only read and edit files\n"
    "inside this directory. Do not walk upward into parent directories.\n"
)


def find_project(repo_url: str) -> dict | None:
    """Registry entry for a repo URL, matched on the last path segment.

    Same matching rule the Linear routing in session_phases.py uses, so a repo that routes
    a ticket correctly also resolves its context correctly.
    """
    if not repo_url:
        return None
    try:
        projects_path = config_loader.PROJECTS_JSON
        if not projects_path.exists():
            return None
        data = json.loads(Path(projects_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("workspace_context: registry unreadable: %s", exc)
        return None

    repo_name = repo_url.rstrip("/").removesuffix(".git").split("/")[-1].lower()
    for p in data.get("projects", []):
        if (p.get("repo") or "").split("/")[-1].lower() == repo_name:
            return p
    return None


def resolve_charter(project: dict) -> tuple[str, str]:
    """Return (charter_text, status) for a project entry.

    status is one of "none" (not declared), "ok", or "missing". "missing" is deliberately
    distinguishable from "none": a declared-but-unresolvable charter is a broken promise
    the workspace should surface, not a project that simply has no charter.
    """
    declared = (project or {}).get("business_charter") or ""
    if not declared:
        return "", "none"

    # Imported lazily: discovery pulls in the wider harness, and this module is imported
    # from the clone phase, which must not depend on that import graph succeeding.
    try:
        from .discovery import CHARTERS_DIR
    except Exception:  # pragma: no cover - defensive
        return "", "missing"

    path = Path(declared)
    if not path.is_absolute():
        candidate = Path(CHARTERS_DIR) / Path(declared).name
        path = candidate if candidate.exists() else path

    if not path.exists():
        return "", "missing"
    try:
        return path.read_text(encoding="utf-8").strip(), "ok"
    except OSError as exc:
        log.warning("workspace_context: charter unreadable at %s: %s", path, exc)
        return "", "missing"


def build_workspace_claude_md(repo_url: str, brief: str = "") -> str:
    """Compose the CLAUDE.md planted at the root of a generated workspace."""
    parts: list[str] = [_GUARD]

    project = find_project(repo_url)
    if project is None:
        parts.append(
            "\n## Project context\n\n"
            f"No `config/harness/projects.json` entry matches `{repo_url or 'unknown repo'}`.\n"
            "Treat the repository itself as the only source of truth for product intent,\n"
            "and do not assume a buyer, a quality bar or an out-of-scope list.\n"
        )
        return "".join(parts) + _brief_section(brief)

    lines = ["\n## Project context\n", f"\n- **Project**: {project.get('id') or 'unknown'}"]
    if project.get("repo"):
        lines.append(f"\n- **Repo**: {project['repo']}")
    stack = project.get("stack") or []
    if stack:
        lines.append(f"\n- **Stack**: {', '.join(str(s) for s in stack)}")
    deployments = project.get("deployments") or {}
    if isinstance(deployments, dict):
        for label, url in deployments.items():
            lines.append(f"\n- **{label.capitalize()}**: {url}")
    lines.append("\n")
    parts.append("".join(lines))

    charter_text, status = resolve_charter(project)
    if status == "ok":
        parts.append(f"\n## Business charter\n\n{charter_text}\n")
    elif status == "missing":
        # Loud on purpose. Omitting the section would make "charter missing" and "project
        # has no charter" produce identical files, which is how this went unnoticed.
        parts.append(
            "\n## Business charter — DECLARED BUT NOT FOUND\n\n"
            f"This project declares `business_charter: {project.get('business_charter')}`,\n"
            "but the file could not be resolved. The business context that should be here\n"
            "is missing — do NOT infer the buyer, the pain or the promise to fill the gap.\n"
            "State the assumption you are working under instead, so it can be corrected.\n"
        )

    return "".join(parts) + _brief_section(brief)


def _brief_section(brief: str) -> str:
    brief = (brief or "").strip()
    if not brief:
        return ""
    return f"\n## This session's assignment\n\n{brief}\n"
