#!/usr/bin/env python3
"""RA-7015 Cap 0 provisioning gate.

Enforces the founder constraint "services/skills/agents may only use provisioned
tools" against the tracked SSOT in fence/provisioned-tools.yaml.

Two checks:
  1. BANNED-TOKEN SCAN (blocking): fail if any banned tool name appears in a
     scanned wiring surface. Needs no per-skill declarations to work.
  2. ALLOW-LIST RECONCILIATION (report-only): warn on any tool declared in
     agentskills.json dependencies.tools[] that is neither provisioned nor
     banned. Dormant until declarations are populated (0/149 today); promote to
     blocking with --strict once they are.

Exit 0 = clean. Exit 1 = a banned token was found (or --strict reconciliation
failure). Report-only findings never change the exit code unless --strict.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("check_provisioning")

REPO_ROOT = Path(__file__).resolve().parent.parent
SSOT_PATH = REPO_ROOT / "fence" / "provisioned-tools.yaml"


@dataclass
class Ssot:
    """Parsed provisioned-tools SSOT."""

    provisioned: set[str]
    banned: dict[str, str]
    include: list[str]
    exclude: list[str]
    aliases: dict[str, str] = field(default_factory=dict)


def load_ssot(path: Path | None = None) -> Ssot:
    """Read and normalise the SSOT into lower-cased lookup structures."""
    path = path or SSOT_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    provisioned: set[str] = set()
    aliases: dict[str, str] = {}
    for entry in data.get("provisioned", []):
        name = entry["name"].lower()
        provisioned.add(name)
        for alias in entry.get("aliases", []):
            aliases[alias.lower()] = name
    banned = {e["name"].lower(): e.get("reason", "") for e in data.get("banned", [])}
    scan = data.get("scan", {})
    return Ssot(
        provisioned=provisioned,
        banned=banned,
        include=scan.get("include", []),
        exclude=scan.get("exclude", []),
        aliases=aliases,
    )


def _is_excluded(rel_path: str, exclude: list[str]) -> bool:
    """True if the repo-relative path matches any exclude glob."""
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in exclude)


def iter_scan_files(ssot: Ssot, root: Path | None = None) -> list[Path]:
    """Resolve include globs minus exclude globs to a sorted file list."""
    root = root or REPO_ROOT
    seen: set[Path] = set()
    for pattern in ssot.include:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if _is_excluded(rel, ssot.exclude):
                continue
            seen.add(path)
    return sorted(seen)


def scan_banned(ssot: Ssot, root: Path | None = None) -> list[tuple[str, int, str, str]]:
    """Return (rel_path, line_no, banned_name, reason) for every banned hit."""
    root = root or REPO_ROOT
    patterns = {
        name: re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        for name in ssot.banned
    }
    hits: list[tuple[str, int, str, str]] = []
    for path in iter_scan_files(ssot, root):
        rel = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            for name, pattern in patterns.items():
                if pattern.search(line):
                    hits.append((rel, line_no, name, ssot.banned[name]))
    return hits


def reconcile_declarations(ssot: Ssot, root: Path | None = None) -> tuple[int, list[str]]:
    """Report tools declared in agentskills.json that are not provisioned.

    Returns (declared_count, offenders). Report-only unless caller enforces.
    """
    root = root or REPO_ROOT
    manifest = root / "agentskills.json"
    if not manifest.exists():
        return 0, []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    declared = 0
    offenders: list[str] = []
    known = ssot.provisioned | set(ssot.aliases) | set(ssot.banned)
    for skill in data.get("skills", []):
        for tool in skill.get("dependencies", {}).get("tools", []) or []:
            declared += 1
            key = tool.lower()
            resolved = ssot.aliases.get(key, key)
            if resolved not in known:
                offenders.append(f"{skill.get('id', '?')} -> {tool}")
    return declared, offenders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RA-7015 provisioning gate")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail on allow-list reconciliation offenders (default report-only).",
    )
    args = parser.parse_args(argv)

    ssot = load_ssot()
    files = iter_scan_files(ssot)
    logger.info("provisioning gate: scanning %d files across %d globs", len(files), len(ssot.include))

    hits = scan_banned(ssot)
    if hits:
        logger.error("BANNED TOOL(S) FOUND — %d hit(s):", len(hits))
        for rel, line_no, name, reason in hits:
            logger.error("  %s:%d  '%s' — %s", rel, line_no, name, reason)
        logger.error("Fix: remove the banned tool. See fence/provisioned-tools.yaml.")
        return 1
    logger.info("banned-token scan: clean (0 hits for %s)", ", ".join(sorted(ssot.banned)))

    declared, offenders = reconcile_declarations(ssot)
    if declared == 0:
        logger.info("allow-list reconciliation: dormant (0 declared tools in agentskills.json).")
    elif offenders:
        level = logger.error if args.strict else logger.warning
        level("allow-list reconciliation: %d unprovisioned declaration(s):", len(offenders))
        for offender in offenders:
            level("  %s", offender)
        if args.strict:
            return 1
    else:
        logger.info("allow-list reconciliation: all %d declared tools provisioned.", declared)

    return 0


if __name__ == "__main__":
    sys.exit(main())
