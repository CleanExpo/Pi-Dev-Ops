#!/usr/bin/env python3
"""Generate the RA-5042 Margot-led Hermes production packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm.hermes_production_unit import build_packet, render_markdown, write_packet


DEFAULT_OUTPUT_DIR = Path(".harness/hermes-production-unit")


def _load_issues(path: Path | None) -> list[dict]:
    if path is None:
        return [
            {
                "id": "RA-5042",
                "title": "Implement Margot-led autonomous Linear production unit for two child Hermes Agents",
                "priority": 2,
                "project": "Pi-Dev-Ops",
                "state": "In Progress",
                "url": "https://linear.app/unite-group/issue/RA-5042",
                "description": "Create child-agent packets with claim rules, evidence gates, and escalation paths.",
            },
            {
                "id": "RA-2142",
                "title": "Implement hourly status reporting and verification loop",
                "priority": 3,
                "project": "Pi-Dev-Ops",
                "state": "Todo",
                "url": "https://linear.app/unite-group/issue/RA-2142",
                "description": "Create a recurring verified progress report loop suitable for NotebookLM/video consumption.",
            },
            {
                "id": "RA-2989",
                "title": "SECURITY+BILLING: leaked secrets and account rotation required",
                "priority": 1,
                "project": "Pi-Dev-Ops",
                "state": "Todo",
                "url": "https://linear.app/unite-group/issue/RA-2989",
                "description": "Human-owned credential rotation and billing/account recovery task; do not automate secrets.",
            },
            {
                "id": "RA-2996",
                "title": "EPIC: Pi-CEO agentic-OS audit and remediation follow-through",
                "priority": 2,
                "project": "Pi-Dev-Ops",
                "state": "Todo",
                "url": "https://linear.app/unite-group/issue/RA-2996",
                "description": "Audit shipped work, verify remaining systemic issues, and split concrete blockers into follow-up tickets.",
            }
        ]
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues-json", type=Path, help="JSON list of Linear-like issue objects")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stdout", action="store_true", help="Print Markdown packet instead of writing files")
    args = parser.parse_args(argv)

    packet = build_packet(_load_issues(args.issues_json))
    if args.stdout:
        print(render_markdown(packet))
        return 0

    md_path, json_path = write_packet(packet, args.output_dir)
    print(json.dumps({"markdown": str(md_path), "json": str(json_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
