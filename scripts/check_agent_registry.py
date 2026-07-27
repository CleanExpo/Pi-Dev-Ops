#!/usr/bin/env python3
"""Validate the governed Nexus shadow agent registry and generated catalogue."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from swarm.nexus.agent_registry import (  # noqa: E402
    RegistryValidationError,
    load_registry,
    render_catalogue,
    validate_catalogue,
    validate_projection_drift,
)


def _paths(root: Path) -> dict[str, Path]:
    return {
        "registry": root / ".harness" / "agents" / "registry.yaml",
        "manifest": root / "agentskills.json",
        "config": root / ".harness" / "config.yaml",
        "catalogue": root / "docs" / "agents" / "README.md",
    }


def _write_if_changed(path: Path, content: str, repo_root: Path) -> bool:
    try:
        relative = path.relative_to(repo_root)
    except ValueError as exc:
        raise RegistryValidationError(
            path, "catalogue-write-path", "catalogue path must stay inside repository"
        ) from exc
    current = repo_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RegistryValidationError(
                path, "catalogue-write-path", "catalogue path must not contain symlinks"
            )
    if not path.resolve(strict=False).is_relative_to(repo_root):
        raise RegistryValidationError(
            path, "catalogue-write-path", "catalogue path resolves outside repository"
        )
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=SCRIPT_REPO_ROOT,
        help="Repository root to validate (default: script repository).",
    )
    parser.add_argument(
        "--write-catalogue",
        action="store_true",
        help="Regenerate docs/agents/README.md; never writes vendor projection trees.",
    )
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    paths = _paths(root)

    try:
        registry = load_registry(paths["registry"], paths["manifest"], paths["config"])
        accepted = validate_projection_drift(root, registry)
        catalogue = render_catalogue(registry)
        changed = False
        if args.write_catalogue:
            changed = _write_if_changed(paths["catalogue"], catalogue, root)
        validate_catalogue(paths["catalogue"], catalogue)
    except RegistryValidationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        reproduce = f"python scripts/check_agent_registry.py --repo-root {root}"
        print(f"reproduce: {reproduce}", file=sys.stderr)
        return 1

    action = "regenerated" if changed else "current"
    print(
        "agent registry: PASS — "
        f"{len(registry.agents)} shadow agents; "
        f"{accepted} accepted projection divergences; catalogue {action}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
