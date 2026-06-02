#!/usr/bin/env python3
"""Route a plain-English founder command to the safest Pi-Dev-Ops build method.

This is a cheap, local pre-flight. It does not call models, mutate repos, create
issues, or start builds. It answers: "which lane should Pi-Dev-Ops use first?"

Usage:
    python scripts/route_build_method.py "https://github.com/can1357/oh-my-pi.git"
    python scripts/route_build_method.py --json "ship it when ready"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from tao.build_router import classify_intent, get_adw_template  # noqa: E402
from tao.repo_intake import write_repo_intake_audit, write_repo_intake_clone_scan, write_repo_intake_scan  # noqa: E402
from tao.skills import skills_for_intent  # noqa: E402


_METHOD_BY_INTENT = {
    "repo-intake": "External repo intake: read-only scan before any build",
    "feature": "Senior engineer feature lane",
    "bug": "Reproduce-diagnose-fix lane",
    "chore": "Maintenance/refactor lane",
    "spike": "Research spike with recommendation, no production changes",
    "hotfix": "Minimal production hotfix lane",
    "ship-it": "Launch-readiness pre-flight; propose-only until approval",
    "launch": "Launch-readiness pre-flight; propose-only until approval",
    "video": "Remotion branded video render lane",
}

_STOP_BY_INTENT = {
    "repo-intake": "Stop after fit recommendation unless a follow-on lane is explicitly justified.",
    "ship-it": "Stop at launch gate until build-ready work is approved.",
    "launch": "Stop at launch gate until build-ready work is approved.",
    "spike": "Stop after written recommendation; do not ship code from the spike.",
}


def route_command(command: str) -> dict[str, Any]:
    """Return deterministic routing metadata for a founder command."""
    intent = classify_intent(command)
    template = get_adw_template(intent)
    skill_names = [skill["name"] for skill in skills_for_intent(intent)]
    first_gate = skill_names[0] if skill_names else "none"

    return {
        "route": intent,
        "build_method": _METHOD_BY_INTENT.get(intent, template.get("name", "Feature Build")),
        "why": _why(intent),
        "first_gate": first_gate,
        "skills": skill_names,
        "workflow": template.get("name", "Feature Build"),
        "steps": template.get("steps", []),
        "next_action": _next_action(intent),
        "verification": _verification(intent),
        "stop_condition": _STOP_BY_INTENT.get(
            intent,
            "Stop only when tests/checks pass, independent review passes, and workflow evidence is finalised.",
        ),
    }


def _why(intent: str) -> str:
    if intent == "repo-intake":
        return "External repositories and capability claims must be scanned before adoption or coding."
    if intent in {"ship-it", "launch"}:
        return "Launch/ship language needs a readiness gate before build execution."
    if intent == "hotfix":
        return "Production-urgent wording requires the smallest safe hotfix path."
    if intent == "bug":
        return "Failure wording requires reproduction and root-cause diagnosis before fixing."
    if intent == "spike":
        return "Research/evaluation wording should produce a recommendation before code changes."
    return "Implementation wording maps to a bounded senior-engineer lane."


def _next_action(intent: str) -> str:
    if intent == "repo-intake":
        return "Clone shallow into a sandbox, inspect README/manifests/CI/docs, classify fit, then recommend a follow-on lane."
    if intent in {"ship-it", "launch"}:
        return "Run ship-it pre-flight: launch-charter, project-audit, launch-review, enhance/debloat proposal."
    if intent == "spike":
        return "Create a scoped spike brief and write findings to .harness/spike-<topic>.md."
    return "Initialise senior-engineer workflow evidence, name expected paths, and run the smallest relevant test first."


def _verification(intent: str) -> str:
    if intent == "repo-intake":
        return "Repo metadata, stack, license, commands, and fit classification are captured without code mutation."
    if intent in {"ship-it", "launch"}:
        return "Audit artifacts exist and no build starts before the approval gate."
    if intent == "spike":
        return "Recommendation cites evidence and names the next build/test path."
    return "Required command evidence plus independent review; validate senior-engineer workflow evidence."


def _format_text(route: dict[str, Any]) -> str:
    lines = [
        f"Route: {route['route']}",
        f"Build method: {route['build_method']}",
        f"Why: {route['why']}",
        f"First gate: {route['first_gate']}",
        f"Workflow: {route['workflow']}",
        f"Steps: {', '.join(route['steps'])}",
        f"Next action: {route['next_action']}",
        f"Verification: {route['verification']}",
        f"Stop condition: {route['stop_condition']}",
    ]
    if route["skills"]:
        lines.append(f"Skills: {', '.join(route['skills'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a command to the safest Pi-Dev-Ops build method.")
    parser.add_argument("command", nargs="+", help="Plain-English command or repository URL to route")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--write-audit",
        action="store_true",
        help="For repo-intake routes, write JSON and Markdown receipts under .harness/audits/repo-intake",
    )
    parser.add_argument(
        "--audits-dir",
        default=str(REPO_ROOT / ".harness" / "audits" / "repo-intake"),
        help="Directory for --write-audit artifacts",
    )
    parser.add_argument(
        "--scan-path",
        default=None,
        help="Optional local sandbox clone/path to read-only scan and merge into the repo-intake audit",
    )
    parser.add_argument(
        "--sandbox-clone",
        action="store_true",
        help="Shallow-clone the source URL into .harness/tmp/repo-intake, then read-only scan and write audit",
    )
    parser.add_argument(
        "--sandbox-dir",
        default=str(REPO_ROOT / ".harness" / "tmp" / "repo-intake"),
        help="Directory for --sandbox-clone shallow clones",
    )
    parser.add_argument(
        "--force-sandbox",
        action="store_true",
        help="Replace an existing sandbox clone for the same source URL",
    )
    args = parser.parse_args(argv)

    command = " ".join(args.command).strip()
    route = route_command(command)
    if args.write_audit or args.scan_path or args.sandbox_clone:
        if route["route"] != "repo-intake":
            print("--write-audit/--scan-path/--sandbox-clone are only valid for repo-intake routes", file=sys.stderr)
            return 2
        if args.sandbox_clone and args.scan_path:
            print("Use either --sandbox-clone or --scan-path, not both", file=sys.stderr)
            return 2
        if args.sandbox_clone:
            artifact = write_repo_intake_clone_scan(command, args.audits_dir, args.sandbox_dir, force=args.force_sandbox)
            route["sandbox_path"] = artifact["clone"]["sandbox_path"]
        elif args.scan_path:
            artifact = write_repo_intake_scan(command, args.audits_dir, args.scan_path)
            route["scan_path"] = str(args.scan_path)
        else:
            artifact = write_repo_intake_audit(command, args.audits_dir)
        route["audit_json_path"] = artifact["json_path"]
        route["audit_markdown_path"] = artifact["markdown_path"]
        route["fit_classification"] = artifact["audit"].get("fit_classification")
    if args.json:
        print(json.dumps(route, indent=2, sort_keys=True))
    else:
        print(_format_text(route))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
