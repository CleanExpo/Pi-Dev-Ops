#!/usr/bin/env python3
"""
specialised_skill_foundation.py — approval-gated specialised skill foundation packets.

Creates a machine-readable foundation packet for a new or amended specialised
skill without mutating the live skill registry. This is the safe first step for
Nexus/Pi-Dev-Ops skill self-development: generate the proposed SKILL.md shape,
evidence contract, routing metadata, and approval gates; a human or later
approved curator flow can decide whether to apply it.

Usage:
    python scripts/specialised_skill_foundation.py \
      --name "Nexus Evidence Ledger" \
      --trigger "When a run needs proof paths before handoff" \
      --evidence lesson-1 --evidence /path/to/source.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = Path(".harness/skill-foundations")
DEFAULT_MANIFEST = Path("agentskills.json")

_FORBIDDEN_SIDE_EFFECTS = [
    "No production DB writes",
    "No deploys",
    "No public publishing",
    "No client communications",
    "No billing or payment actions",
    "No secrets, password, token, or credential rotation",
]

_APPROVAL_BLOCKED_REASON = "human_review_required_before_live_skill_mutation"


def slugify_skill_name(name: str) -> str:
    """Return a lowercase, hyphenated, filesystem-safe skill name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:64].strip("-") or "specialised-skill"


def _normalise_trigger(trigger: str) -> str:
    trigger = " ".join(trigger.strip().split())
    if not trigger:
        return "When a repeated Nexus/Pi-Dev-Ops workflow needs a bounded specialised procedure."
    return trigger


def _load_existing_skills(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    skills = data.get("skills", [])
    return [s for s in skills if isinstance(s, dict)]


_STOP_TOKENS = {
    "the", "and", "for", "with", "when", "needs", "need", "run", "task", "work",
    "before", "after", "from", "into", "this", "that", "skill", "skills", "use",
    "uses", "using", "output", "outputs", "path", "paths",
}


def _token_set(text: str) -> set[str]:
    return {
        t
        for t in re.split(r"[^a-z0-9]+", text.lower())
        if len(t) > 2 and t not in _STOP_TOKENS
    }


def find_nearest_existing_skill(name: str, trigger: str, skills: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Cheap deterministic overlap check; enough for proposal triage.

    The packet stays approval-gated either way. This only decides whether the
    recommended action should be to amend an existing skill first.
    """
    wanted = _token_set(f"{name} {trigger}")
    best: tuple[int, dict[str, Any] | None] = (0, None)
    for skill in skills:
        haystack = f"{skill.get('id', '')} {skill.get('description', '')} {skill.get('path', '')}"
        score = len(wanted & _token_set(haystack))
        if score > best[0]:
            best = (score, skill)
    return best[1] if best[0] >= 1 else None


def _description_from_trigger(trigger: str) -> str:
    cleaned = trigger.rstrip(".").strip()
    if cleaned.lower().startswith("when "):
        return f"Use {cleaned[5:]}"
    return f"Use when {cleaned}"


def _draft_skill_md(skill_name: str, display_name: str, trigger: str, evidence: list[str]) -> str:
    evidence_lines = "\n".join(f"- {item}" for item in evidence) if evidence else "- DATA_REQUIRED: add evidence before approval."
    forbidden_lines = "\n".join(f"- {item}" for item in _FORBIDDEN_SIDE_EFFECTS)
    description = _description_from_trigger(trigger)
    return f"""---
name: {skill_name}
description: "{description}"
when_to_use: "{trigger}"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash
owner_role: "Curator"
status: "proposed"
automation: manual
---

# {display_name}

## Purpose

Provide the specialised, repeatable procedure for this class of Nexus/Pi-Dev-Ops work. This is a foundation draft, not a live activated skill, until a human approves it and the registry/manifest tests pass.

## When to Use

- {trigger}
- Use only when the evidence shows this is a repeated workflow or a durable specialised lane.
- Prefer amending an existing umbrella skill when one already covers the trigger.

## Evidence Foundation

{evidence_lines}

## Operating Procedure

1. Load the relevant repo/vault/source evidence first.
2. Confirm whether an existing skill already covers the work.
3. If an existing skill covers it, propose an amendment instead of creating a sibling.
4. Define the specialist lane, allowed tools, forbidden side effects, and verification evidence.
5. Produce a reviewable artifact: plan, diff, test output, evidence paths, and handoff notes.
6. Do not mutate the live skill registry until approval is recorded.

## Safety Boundaries

{forbidden_lines}
- Any live skill creation or mutation requires explicit human approval.

## Verification Checklist

- [ ] Trigger is precise enough for routing.
- [ ] Existing skill registry was checked for duplicates.
- [ ] Evidence has at least one concrete source path, lesson ID, PR, issue, or outcome.
- [ ] Allowed tools are narrow enough for the task.
- [ ] Forbidden side effects are explicit.
- [ ] Tests or deterministic verification commands are listed before activation.
"""


def build_foundation_packet(
    name: str,
    trigger: str,
    evidence: list[str] | None = None,
    repo_root: Path | str = REPO_ROOT,
    existing_manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build an approval-gated foundation packet for a specialised skill."""
    root = Path(repo_root)
    trigger = _normalise_trigger(trigger)
    evidence = [str(e).strip() for e in (evidence or []) if str(e).strip()]
    skill_name = slugify_skill_name(name)
    manifest_path = Path(existing_manifest_path) if existing_manifest_path else root / DEFAULT_MANIFEST
    existing_skills = _load_existing_skills(manifest_path)
    nearest = find_nearest_existing_skill(name, trigger, existing_skills)
    recommended = "amend_existing_skill" if nearest else "create_new_skill_candidate"

    packet = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "need_approval",
        "blocked_reason": _APPROVAL_BLOCKED_REASON,
        "recommended_action": recommended,
        "proposed_skill_name": skill_name,
        "display_name": name.strip() or skill_name,
        "trigger": trigger,
        "evidence": evidence,
        "nearest_existing_skill": nearest,
        "draft_skill_path": f"skills/{skill_name}/SKILL.md",
        "draft_skill_md": _draft_skill_md(skill_name, name.strip() or skill_name, trigger, evidence),
        "routing_metadata": {
            "when_to_use": trigger,
            "invocation_mode": "manual_until_approved",
            "context_tier": "warm",
            "specialist": "nexus-skill-curator",
            "allowed_tools": ["Read", "Glob", "Grep", "Bash"],
        },
        "approval_contract": {
            "approval_required_to_create": True,
            "approval_required_to_amend": True,
            "may_write_live_skill": False,
            "may_update_manifest": False,
            "may_enable_auto_routing": False,
        },
        "next_steps_after_approval": [
            "Write draft_skill_md to draft_skill_path or amend nearest_existing_skill.",
            "Run python -m swarm.agentskills_manifest.",
            "Run focused skill/router tests.",
            "Regenerate router index and gap report.",
            "Commit packet + skill/manifest/router changes together.",
        ],
    }
    return packet


def write_foundation_packet(packet: dict[str, Any], repo_root: Path | str = REPO_ROOT) -> Path:
    root = Path(repo_root)
    out_dir = root / DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    skill_name = packet.get("proposed_skill_name") or "specialised-skill"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}-{skill_name}.json"
    out_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create approval-gated specialised skill foundation packet")
    parser.add_argument("--name", required=True, help="Proposed specialised skill name")
    parser.add_argument("--trigger", required=True, help="Precise when-to-use trigger")
    parser.add_argument("--evidence", action="append", default=[], help="Evidence path/ID; repeatable")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repo root for output and manifest lookup")
    parser.add_argument("--manifest", default=None, help="Optional agentskills.json path")
    parser.add_argument("--print", action="store_true", help="Print packet JSON after writing")
    args = parser.parse_args(argv)

    packet = build_foundation_packet(
        name=args.name,
        trigger=args.trigger,
        evidence=args.evidence,
        repo_root=Path(args.repo_root),
        existing_manifest_path=Path(args.manifest) if args.manifest else None,
    )
    out = write_foundation_packet(packet, Path(args.repo_root))
    print(f"wrote {out}")
    if args.print:
        print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
