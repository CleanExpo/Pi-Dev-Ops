#!/usr/bin/env python3
"""NEXUS DEEP advisory intake and status, NOT an authorization or release controller.

This CLI never invokes a model, executes user-supplied shell, signs a receipt,
sends network traffic, changes Git, or grants permission. It records proposals.
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIERS = ("T0", "T1", "T2", "T3")


def head(repo: Path) -> str:
    if not repo.is_dir():
        raise ValueError("repository path is not a directory")
    cmd = subprocess.run(["git", "-C", str(repo.resolve()), "rev-parse", "--show-toplevel", "HEAD"],
                         capture_output=True, text=True, timeout=10, check=False)
    if cmd.returncode != 0:
        raise ValueError("cannot verify Git worktree and HEAD")
    lines = cmd.stdout.strip().splitlines()
    if len(lines) != 2 or str(repo.resolve()) != str(Path(lines[0]).resolve()):
        raise ValueError("repository path must be exact Git worktree root")
    sha = lines[1].strip()
    if len(sha) not in (40, 64) or any(x not in "0123456789abcdef" for x in sha):
        raise ValueError("invalid Git commit ID")
    return sha


def init_task(repo: Path, objective: str, tier: str, out: Path, budget_aud=None) -> dict:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("nonempty objective required")
    if tier not in TIERS:
        raise ValueError("unknown risk tier")
    if budget_aud is not None and (not math.isfinite(budget_aud) or budget_aud < 0):
        raise ValueError("invalid proposed budget")
    sha = head(repo)
    manifest = {
        "schema": "nexus-deep/advisory-task/1",
        "task_id": str(uuid.uuid4()),
        "objective": objective,
        "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
        "git_head": sha,
        "repo_observed": str(repo.resolve()),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "tier_proposed": tier,
        "tier_authoritative": False,
        "budget_aud_proposed": budget_aud,
        "authorization_status": "PROPOSAL",
        "execution_status": "NOT_STARTED",
        "receipts_unverified": [],
        "warning": "PROPOSAL ONLY. No task admitted, tests executed, or permission granted."
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, allow_nan=False)
        file.write("\n")
    return manifest


def status_task(manifest_path: Path, policy_path: Path = HERE / "policy.json") -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != "nexus-deep/advisory-task/1":
        raise ValueError("invalid manifest schema")
    if not isinstance(policy, dict) or policy.get("enforcement") != "ADVISORY_ONLY":
        raise ValueError("unknown or unsafe policy")
    tier = manifest.get("tier_proposed")
    tiers = policy.get("tiers")
    if not isinstance(tiers, dict) or tier not in tiers:
        raise ValueError("unknown tier")
    required = tiers[tier].get("required") if isinstance(tiers[tier], dict) else None
    if not isinstance(required, list) or not all(isinstance(g, str) for g in required):
        raise ValueError("malformed policy: required gates must be a list of names")
    state = "UNKNOWN"
    try:
        state = "MATCH" if head(Path(manifest["repo_observed"])) == manifest["git_head"] else "STALE_SHA"
    except (ValueError, KeyError, TypeError):
        state = "UNVERIFIED"
    return {
        "decision": "ENFORCEMENT_UNPROVEN",
        "task_id": manifest.get("task_id"),
        "risk_tier_proposed": tier,
        "sha_state": state,
        "authorization_status": "PROPOSAL",
        "required_independent_gates": required,
        "untrusted_receipt_count": len(manifest.get("receipts_unverified", [])) if isinstance(manifest.get("receipts_unverified"), list) else 0,
        "warning": "This CLI does not validate receipts or approve work; verify with independently protected CI."
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    setup = sub.add_parser("init")
    setup.add_argument("--repo", type=Path, required=True)
    setup.add_argument("--task", required=True)
    setup.add_argument("--tier", choices=TIERS, required=True)
    setup.add_argument("--out", type=Path, required=True)
    setup.add_argument("--budget-aud", type=float)
    check = sub.add_parser("status")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--policy", type=Path, default=HERE / "policy.json")
    args = parser.parse_args(argv)
    try:
        if args.mode == "init":
            record = init_task(args.repo, args.task, args.tier, args.out, args.budget_aud)
            result = {"decision": "PROPOSED", "manifest": str(args.out),
                      "task_id": record["task_id"], "git_head": record["git_head"]}
        else:
            result = status_task(args.manifest, args.policy)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, FileNotFoundError, FileExistsError, KeyError,
            TypeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print(json.dumps({"decision": "BLOCKED", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
