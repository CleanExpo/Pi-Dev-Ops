#!/usr/bin/env python3
"""Senior Engineer Dynamic Workflow gate runner for Pi-Dev-Ops.

This runner makes Anthropic Dynamic Workflow discipline operational without
requiring the platform runtime to consume Anthropic API credits. It does not
write code for the agent; it enforces that each build lane has a manifest,
connection map, verification evidence, independent review, and final state
before the lane can be marked complete.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_MANIFEST = ROOT / ".harness" / "workflows" / "templates" / "senior-engineer-build-loop.manifest.json"
TEMPLATE_EVIDENCE = ROOT / ".harness" / "workflows" / "templates" / "senior-engineer-evidence.md"
RUNS_DIR = ROOT / ".harness" / "workflows" / "runs"
VALIDATOR = ROOT / ".harness" / "workflows" / "validate_workflow_evidence.py"


def _slug(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe[:72] or "workflow-run"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _git_branch() -> str:
    result = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() or "unknown"


def _git_changed_files() -> list[str]:
    result = subprocess.run(["git", "status", "--short", "--untracked-files=all"], cwd=ROOT, text=True, capture_output=True, check=False)
    files: list[str] = []
    for line in result.stdout.splitlines():
        if line.strip():
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            files.append(path.replace("\\", "/"))
    return files


def init_run(args: argparse.Namespace) -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_json(TEMPLATE_MANIFEST)
    manifest["repo"] = str(ROOT)
    manifest["ticket"] = args.ticket
    manifest["intent"] = args.intent
    manifest["risk"] = args.risk
    manifest["scope"]["expected_change_paths"] = args.expected_path or []
    manifest["verification"]["required_commands"] = args.required_command or []

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{_slug(args.intent)}"
    manifest_path = RUNS_DIR / f"{run_id}.manifest.json"
    evidence_path = RUNS_DIR / f"{run_id}.md"
    manifest["verification"]["evidence_path"] = str(evidence_path.relative_to(ROOT)).replace("\\", "/")

    _write_json(manifest_path, manifest)
    evidence = TEMPLATE_EVIDENCE.read_text(encoding="utf-8")
    evidence = evidence.replace("- Workflow ID:", f"- Workflow ID: {manifest['workflow_id']}")
    evidence = evidence.replace("- Date:", f"- Date: {stamp}")
    evidence = evidence.replace("- Operator:", "- Operator: Pi-Dev-Ops senior-engineer workflow")
    evidence = evidence.replace("- Repo:", f"- Repo: {ROOT}")
    evidence = evidence.replace("- Branch:", f"- Branch: {_git_branch()}")
    evidence = evidence.replace("- Ticket / request:", f"- Ticket / request: {args.ticket or 'none'}")
    evidence = evidence.replace("- Intent:", f"- Intent: {args.intent}")
    evidence = evidence.replace("- Risk:", f"- Risk: {args.risk}")
    evidence_path.write_text(evidence, encoding="utf-8")

    print(f"manifest={manifest_path}")
    print(f"evidence={evidence_path}")
    return 0


def status_run(args: argparse.Namespace) -> int:
    manifest = _load_json(Path(args.manifest))
    evidence = Path(args.evidence)
    expected = manifest.get("scope", {}).get("expected_change_paths", [])
    changed = _git_changed_files()
    print("Senior-engineer workflow status")
    print(f"workflow_id={manifest.get('workflow_id')}")
    print(f"evidence={evidence}")
    print(f"changed_files={len(changed)}")
    if changed:
        for path in changed:
            mark = "expected" if not expected or any(Path(path).match(pat) for pat in expected) else "outside-expected"
            print(f"- {path} [{mark}]")
    return 0


def validate_run(args: argparse.Namespace) -> int:
    if not VALIDATOR.exists():
        print(f"validator missing: {VALIDATOR}", file=sys.stderr)
        return 1
    cmd = [sys.executable, str(VALIDATOR), str(Path(args.manifest)), str(Path(args.evidence))]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode


def install_ci(args: argparse.Namespace) -> int:
    workflow_dir = ROOT / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    target = workflow_dir / "senior-engineer-workflow.yml"
    if target.exists() and not args.force:
        print(f"exists={target}")
        return 0
    target.write_text(
        "name: senior-engineer-workflow\n"
        "on:\n"
        "  pull_request:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  validate-workflow-evidence:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.11'\n"
        "      - name: Compile workflow gate scripts\n"
        "        run: python -m py_compile .harness/workflows/validate_workflow_evidence.py .harness/workflows/senior_engineer_workflow.py\n"
        "      - name: Run workflow gate tests\n"
        "        run: python -m pytest tests/test_workflow_evidence.py -q\n"
        "      - name: Validate touched workflow run evidence\n"
        "        shell: bash\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        "          base_ref=\"${{ github.base_ref || 'main' }}\"\n"
        "          git fetch --no-tags --depth=1 origin \"$base_ref\" || true\n"
        "          mapfile -t manifests < <(git diff --name-only \"origin/${base_ref}...HEAD\" -- '.harness/workflows/runs/*.manifest.json')\n"
        "          for manifest in \"${manifests[@]}\"; do\n"
        "            evidence=\"${manifest%.manifest.json}.md\"\n"
        "            if [[ ! -f \"$evidence\" ]]; then\n"
        "              echo \"Missing evidence file for $manifest\" >&2\n"
        "              exit 1\n"
        "            fi\n"
        "            python .harness/workflows/validate_workflow_evidence.py \"$manifest\" \"$evidence\"\n"
        "          done\n",
        encoding="utf-8",
    )
    print(f"installed={target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pi-Dev-Ops senior-engineer workflow gate runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="create a run manifest and evidence file")
    init.add_argument("--intent", default="feature")
    init.add_argument("--risk", default="medium")
    init.add_argument("--ticket", default=None)
    init.add_argument("--expected-path", action="append")
    init.add_argument("--required-command", action="append")
    init.set_defaults(func=init_run)

    status = sub.add_parser("status", help="summarise current diff against a run manifest")
    status.add_argument("manifest")
    status.add_argument("evidence")
    status.set_defaults(func=status_run)

    validate = sub.add_parser("validate", help="run the strict evidence validator")
    validate.add_argument("manifest")
    validate.add_argument("evidence")
    validate.set_defaults(func=validate_run)

    ci = sub.add_parser("install-ci", help="install the lightweight CI guard")
    ci.add_argument("--force", action="store_true")
    ci.set_defaults(func=install_ci)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
