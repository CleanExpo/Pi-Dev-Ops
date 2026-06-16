#!/usr/bin/env python3
"""Run the capability intelligence loop end to end.

Default behavior:
1. Fetch fresh capability discoveries.
2. Write report/source/manifest/CRM-intake files to the second brain.
3. Validate the CRM intake payload.

CRM posting is opt-in via --post or UNITE_CRM_CAPABILITY_POST=1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import capability_crm_import, capability_scout


def enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run capability scout -> Brain -> CRM intake validation.")
    parser.add_argument("--limit", type=int, default=capability_scout.DEFAULT_LIMIT)
    parser.add_argument("--min-score", type=int, default=45)
    parser.add_argument("--brain-root", type=Path, default=capability_scout.DEFAULT_BRAIN_ROOT)
    parser.add_argument("--projects", type=Path, default=capability_scout.PROJECTS_JSON)
    parser.add_argument("--crm-url", default=capability_crm_import.DEFAULT_CRM_URL)
    parser.add_argument("--token-env", default=capability_crm_import.DEFAULT_TOKEN_ENV)
    parser.add_argument("--post", action="store_true", help="POST validated proposals to CRM.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    profiles = capability_scout.load_project_profiles(args.projects)
    discoveries = capability_scout.fetch_live_discoveries(args.limit)
    candidates = [
        candidate for candidate in capability_scout.build_candidates(discoveries, profiles)
        if candidate.relevance_score >= args.min_score
    ]
    brain = capability_scout.write_brain_outputs(candidates, args.brain_root)
    proposals = capability_crm_import.validate_proposals(
        capability_crm_import.load_manifest_or_jsonl(Path(str(brain["manifest_path"]))),
    )
    should_post = args.post or enabled(os.environ.get("UNITE_CRM_CAPABILITY_POST"))

    result: dict[str, Any] = {
        "ok": True,
        "discoveries": len(discoveries),
        "candidates": len(candidates),
        "brain": brain,
        "crm_import": {
            "mode": "post" if should_post else "dry-run",
            "proposal_count": len(proposals),
        },
    }
    if should_post:
        result["crm_import"]["response"] = capability_crm_import.post_to_crm(
            proposals,
            url=args.crm_url,
            token=os.environ.get(args.token_env),
        )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    try:
        result = run_loop(args)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(
                "Capability loop: "
                f"{result['discoveries']} discoveries, "
                f"{result['candidates']} candidates, "
                f"CRM {result['crm_import']['mode']}"
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Capability loop failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
