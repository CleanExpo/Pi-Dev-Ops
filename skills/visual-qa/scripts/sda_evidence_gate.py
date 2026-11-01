#!/usr/bin/env python3
"""Fail-closed SDA structural evidence, NOT human design or rights approval.

Uses descriptor-confined source files, independently scoped screenshots,
actual media decoding and immutable exact-SHA acceptance records.
"""
import argparse
import os
import sys
from pathlib import Path

from sda_gate_core import (
    RUBRIC, VIEWPORTS, EvidenceAssets, _pinned_root_dir,
    _read_held_file, strict_json,
)
from sda_gate_browser import validate_browser
from sda_gate_release import validate_release


def check(manifest_file, release=False, baseline_record=None, scope_record=None):
    errors = []
    # Preserve user-controlled symlinks for O_NOFOLLOW. Only normalise the
    # fixed macOS system aliases (/var, /tmp, /etc) to their /private roots;
    # resolving the whole path would silently follow a malicious evidence link.
    supplied = Path(manifest_file)
    # Path.absolute() preserves '..', while scope and baseline records are
    # resolved. Reject traversal before comparing candidate and record roots.
    if ".." in supplied.parts:
        return ["noncanonical manifest path: parent traversal is forbidden"]
    manifest = supplied.absolute()
    if sys.platform == "darwin" and len(manifest.parts) > 2:
        alias = manifest.parts[1]
        if alias in ("var", "tmp", "etc"):
            root_alias = Path("/") / alias
            if root_alias.is_symlink() and root_alias.resolve() == Path("/private") / alias:
                manifest = Path("/private", alias, *manifest.parts[2:])
    root = manifest.parent
    try:
        rootfd = _pinned_root_dir(root)
    except (OSError, ValueError) as exc:
        return ["evidence root cannot be securely opened: " + str(exc)]
    try:
        doc = strict_json(_read_held_file(rootfd, [manifest.name], 4 * 1024 * 1024).decode("utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("manifest must be an object")
    except (OSError, ValueError) as exc:
        os.close(rootfd)
        return ["manifest missing or invalid: " + str(exc)]
    try:
        if doc.get("schema_version") != 1:
            errors.append("schema_version must equal 1")
        assets = EvidenceAssets(rootfd, errors)
        validate_browser(doc, root, scope_record, assets, errors)
        if release:
            validate_release(doc, root, baseline_record, assets, errors)
    finally:
        os.close(rootfd)
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="JSON manifest with SHA256 of evidence")
    parser.add_argument("--release", action="store_true", help="require actual creative, rights and founder records")
    parser.add_argument("--baseline-record", type=Path, help="separately frozen prior approved SHA record, outside candidate folder")
    parser.add_argument("--scope-record", type=Path, required=True, help="independent captured-page inventory outside candidate directory")
    args = parser.parse_args()
    errors = check(args.manifest, args.release, args.baseline_record, args.scope_record)
    if errors:
        print("SDA HOLD: " + str(len(errors)) + " unmet evidence condition(s)")
        for error in errors:
            print("  - " + error)
        return 2
    print("SDA EVIDENCE PASS (" + ("release" if args.release else "technical") + "); human review still independently required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
