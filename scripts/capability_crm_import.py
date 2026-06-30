#!/usr/bin/env python3
"""Validate and optionally post capability scout CRM intake proposals.

The capability scout writes a JSONL bridge into the second brain. This runner is
the explicit handoff into Unite-Group CRM: dry-run validates the payload; posting
sends the same blocked, approval-required proposals to the CRM intake route.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CRM_URL = "http://localhost:3000/api/command-center/control-panel/capability-intake"
DEFAULT_TOKEN_ENV = "UNITE_CRM_ADMIN_TOKEN"
REQUIRED_FIELDS = {
    "title",
    "description",
    "status",
    "priority",
    "assignee_name",
    "tags",
    "obsidian_path",
    "source_url",
    "project_matches",
    "capability_type",
    "relevance_score",
    "hermes_lane",
}
VALID_PRIORITIES = {"urgent", "high", "medium", "normal", "low"}
VALID_HERMES_LANES = {"engineering", "research-ops", "content-systems", "watchlist"}


class IntakeError(ValueError):
    pass


def load_manifest_or_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise IntakeError(f"input_not_found:{path}")

    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("crm_tasks"), list):
            return [dict(item) for item in data["crm_tasks"] if isinstance(item, dict)]
        if isinstance(data, dict) and data.get("crm_bridge_path"):
            return load_manifest_or_jsonl(Path(str(data["crm_bridge_path"])))
        raise IntakeError("manifest_missing_crm_tasks")

    proposals: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IntakeError(f"invalid_jsonl_line:{line_no}") from exc
        if not isinstance(item, dict):
            raise IntakeError(f"invalid_jsonl_record:{line_no}")
        proposals.append(dict(item))
    return proposals


def validate_proposal(proposal: dict[str, Any], index: int) -> dict[str, Any]:
    missing = sorted(REQUIRED_FIELDS - set(proposal))
    if missing:
        raise IntakeError(f"proposal_{index}_missing:{','.join(missing)}")

    if proposal["status"] != "blocked":
        raise IntakeError(f"proposal_{index}_status_not_blocked")
    if proposal["priority"] not in VALID_PRIORITIES:
        raise IntakeError(f"proposal_{index}_invalid_priority")
    if proposal["hermes_lane"] not in VALID_HERMES_LANES:
        raise IntakeError(f"proposal_{index}_invalid_hermes_lane")
    if not isinstance(proposal["relevance_score"], int) or not 0 <= proposal["relevance_score"] <= 100:
        raise IntakeError(f"proposal_{index}_invalid_relevance_score")

    tags = proposal["tags"]
    projects = proposal["project_matches"]
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag for tag in tags):
        raise IntakeError(f"proposal_{index}_invalid_tags")
    if not {"capability-scout", "approval-required", "hermes-intake"}.issubset(set(tags)):
        raise IntakeError(f"proposal_{index}_missing_required_tags")
    if not isinstance(projects, list) or not all(isinstance(project, str) and project for project in projects):
        raise IntakeError(f"proposal_{index}_invalid_project_matches")

    for key in ["title", "description", "assignee_name", "obsidian_path", "source_url", "capability_type"]:
        if not isinstance(proposal[key], str) or not proposal[key].strip():
            raise IntakeError(f"proposal_{index}_invalid_{key}")

    return proposal


def validate_proposals(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not proposals:
        raise IntakeError("empty_intake")
    if len(proposals) > 50:
        raise IntakeError("too_many_proposals")
    return [validate_proposal(proposal, index) for index, proposal in enumerate(proposals, start=1)]


def post_to_crm(proposals: list[dict[str, Any]], *, url: str, token: str | None) -> dict[str, Any]:
    body = json.dumps({"tasks": proposals}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise IntakeError(f"crm_http_{exc.code}:{detail}") from exc
    except urllib.error.URLError as exc:
        raise IntakeError(f"crm_unreachable:{exc.reason}") from exc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import capability scout JSONL into Unite-Group CRM.")
    parser.add_argument("input", type=Path, help="Capability scout manifest JSON or CRM intake JSONL.")
    parser.add_argument("--crm-url", default=DEFAULT_CRM_URL, help="Unite-Group capability intake route.")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="Environment variable containing CRM bearer token.")
    parser.add_argument("--post", action="store_true", help="POST to CRM. Omitted means validate-only dry-run.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    try:
        proposals = validate_proposals(load_manifest_or_jsonl(args.input))
        result: dict[str, Any] = {
            "ok": True,
            "mode": "post" if args.post else "dry-run",
            "proposal_count": len(proposals),
            "top": proposals[:3],
        }
        if args.post:
            result["crm"] = post_to_crm(
                proposals,
                url=args.crm_url,
                token=os.environ.get(args.token_env),
            )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Capability CRM import {result['mode']}: {len(proposals)} proposal(s) valid")
            if args.post:
                print(json.dumps(result["crm"], indent=2))
        return 0
    except (IntakeError, OSError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Capability CRM import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
