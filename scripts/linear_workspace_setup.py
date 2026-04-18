#!/usr/bin/env python3
"""
linear_workspace_setup.py — Idempotent Pi-Dev workspace setup for Linear.

Creates the 4 workflow statuses and 7 labels required by the Pi-Dev × Linear
Contract (skills/pi-dev-linear-contract/SKILL.md, Part 1 — RA-1298 / RA-1370).

Workflow states are team-scoped in Linear — applying to one team covers all
projects within it.  Labels are created workspace-wide where the API key
permits; falls back to team-scoped with a manual-promotion note.

Usage:
    LINEAR_API_KEY=lin_api_... python scripts/linear_workspace_setup.py
    LINEAR_API_KEY=lin_api_... python scripts/linear_workspace_setup.py \\
        --team-id a8a52f07-63cf-4ece-9ad2-3e3bd3c15673 --dry-run

Rollout order (RA-1298):
  Week 1 — run against ONE team (default: RA team, covers Pi-Dev-Ops +
            RestoreAssist).  Verify in UI.  Then wire Skill 4 (read-only).

Exit codes:
  0 — all automatable items are in place (manual steps noted but expected).
  1 — API error; at least one state or label could not be created.

Note: The 'Pi-Dev Run ID' custom field always requires the Linear UI — it is
not exposed in the standard GraphQL API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# ── Config ─────────────────────────────────────────────────────────────────────

# Default: RA team (Pi-Dev-Ops project f45212be + RestoreAssist project 3c78358a)
DEFAULT_TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"

LINEAR_API = "https://api.linear.app/graphql"

# Pi-Dev × Linear Contract §1 — workflow statuses (per team)
# (name, linear_type, hex_color)
# Valid types: triage | backlog | unstarted | started | completed | cancelled
REQUIRED_STATES: list[tuple[str, str, str]] = [
    ("Ready for Pi-Dev",    "unstarted", "#e2e2e2"),
    ("Pi-Dev: In Progress", "started",   "#4ea7fc"),
    ("Pi-Dev: Blocked",     "started",   "#f2994a"),
    ("In Review",           "started",   "#9b59b6"),
]

# Pi-Dev × Linear Contract §2 — workspace labels
# (name, hex_color)
REQUIRED_LABELS: list[tuple[str, str]] = [
    ("pi-dev:source",                        "#7C3AED"),  # Purple  — created by Pi-Dev-Ops
    ("pi-dev:autonomous",                    "#EA580C"),  # Orange  — runnable without sign-off
    ("pi-dev:needs-review",                  "#CA8A04"),  # Yellow  — must stop at In Review
    ("pi-dev:blocked-reason:credentials",    "#DC2626"),  # Red
    ("pi-dev:blocked-reason:ambiguous-spec", "#DC2626"),  # Red
    ("pi-dev:blocked-reason:external-dep",   "#DC2626"),  # Red
    ("pi-dev:blocked-reason:scope-creep",    "#DC2626"),  # Red
]


# ── GraphQL helper ─────────────────────────────────────────────────────────────

def _gql(api_key: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_API,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Workflow state helpers ─────────────────────────────────────────────────────

def _fetch_states(api_key: str, team_id: str) -> dict[str, dict]:
    """Return {name_lower: node} for all workflow states in the team."""
    q = """
query GetTeamStates($teamId: String!) {
  team(id: $teamId) {
    states { nodes { id name type position } }
  }
}"""
    result = _gql(api_key, q, {"teamId": team_id})
    nodes = (
        (result.get("data") or {})
        .get("team", {})
        .get("states", {})
        .get("nodes", [])
    )
    return {n["name"].lower(): n for n in nodes}


def _create_state(
    api_key: str,
    team_id: str,
    name: str,
    state_type: str,
    color: str,
) -> str | None:
    """Create a workflow state.  Returns the new state ID, or None on failure."""
    mutation = """
mutation CreateWorkflowState(
  $teamId: String!
  $name: String!
  $type: String!
  $color: String!
) {
  workflowStateCreate(input: {
    teamId: $teamId
    name: $name
    type: $type
    color: $color
  }) {
    success
    workflowState { id name }
  }
}"""
    result = _gql(api_key, mutation, {
        "teamId": team_id,
        "name": name,
        "type": state_type,
        "color": color,
    })
    payload = (result.get("data") or {}).get("workflowStateCreate", {})
    if payload.get("success"):
        return payload["workflowState"]["id"]
    errors = result.get("errors") or []
    print(f"    response errors: {errors}", file=sys.stderr)
    return None


# ── Label helpers ──────────────────────────────────────────────────────────────

def _fetch_labels(api_key: str) -> dict[str, dict]:
    """Return {name_lower: node} for all labels visible to this key."""
    q = """
query GetAllLabels {
  issueLabels(first: 250) {
    nodes { id name color team { id } }
  }
}"""
    result = _gql(api_key, q, {})
    nodes = (result.get("data") or {}).get("issueLabels", {}).get("nodes", [])
    return {n["name"].lower(): n for n in nodes}


def _create_label(
    api_key: str,
    name: str,
    color: str,
    team_id: str | None = None,
) -> str | None:
    """Create a label.  Workspace-level when team_id is None.  Returns ID or None."""
    if team_id:
        mutation = """
mutation CreateTeamLabel($name: String!, $color: String!, $teamId: String!) {
  issueLabelCreate(input: { name: $name, color: $color, teamId: $teamId }) {
    success
    issueLabel { id name }
  }
}"""
        variables: dict = {"name": name, "color": color, "teamId": team_id}
    else:
        mutation = """
mutation CreateWorkspaceLabel($name: String!, $color: String!) {
  issueLabelCreate(input: { name: $name, color: $color }) {
    success
    issueLabel { id name }
  }
}"""
        variables = {"name": name, "color": color}

    result = _gql(api_key, mutation, variables)
    payload = (result.get("data") or {}).get("issueLabelCreate", {})
    if payload.get("success"):
        return payload["issueLabel"]["id"]
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:  # noqa: PLR0912 (complexity ok for a setup script)
    parser = argparse.ArgumentParser(
        description="Pi-Dev Linear workspace setup (RA-1298 / RA-1370)",
    )
    parser.add_argument(
        "--team-id",
        default=DEFAULT_TEAM_ID,
        help="Linear team ID to apply workflow states to (default: RA team)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report current state without creating anything",
    )
    args = parser.parse_args()

    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        print("ERROR: LINEAR_API_KEY is not set.", file=sys.stderr)
        return 1

    team_id: str = args.team_id
    dry_run: bool = args.dry_run

    print("Pi-Dev Linear workspace setup  (RA-1298 / RA-1370)")
    print(f"Team ID  : {team_id}")
    print(f"Dry run  : {dry_run}")
    print()

    exit_code = 0

    # ── 1. Workflow states ────────────────────────────────────────────────────
    print("=== Workflow States ===")
    try:
        existing_states = _fetch_states(api_key, team_id)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"ERROR: HTTP {exc.code} fetching states — {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR fetching workflow states: {exc}", file=sys.stderr)
        return 1

    print(f"  {len(existing_states)} existing state(s) found in team.")
    for name, state_type, color in REQUIRED_STATES:
        key = name.lower()
        if key in existing_states:
            node = existing_states[key]
            print(f"  ✅ EXISTS   '{name}'  (id={node['id']}, type={node['type']})")
        elif dry_run:
            print(f"  ⬜ PENDING  '{name}'  (type={state_type}, color={color})")
        else:
            state_id = _create_state(api_key, team_id, name, state_type, color)
            if state_id:
                print(f"  ✅ CREATED  '{name}'  (id={state_id})")
            else:
                print(f"  ❌ FAILED   '{name}'  — check permissions (see stderr)")
                exit_code = 1

    if not dry_run and exit_code == 0:
        print()
        print("  NOTE: States are appended at the end of their type group.")
        print("        Re-order them in Linear UI: Settings → Workflows → drag to position.")
        print("        Correct order: Ready for Pi-Dev → Todo → … → In Progress →")
        print("                       Pi-Dev: In Progress → Pi-Dev: Blocked → In Review")

    # ── 2. Labels ─────────────────────────────────────────────────────────────
    print()
    print("=== Labels ===")
    try:
        existing_labels = _fetch_labels(api_key)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"ERROR: HTTP {exc.code} fetching labels — {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR fetching labels: {exc}", file=sys.stderr)
        return 1

    print(f"  {len(existing_labels)} existing label(s) found.")
    label_manual: list[str] = []

    for name, color in REQUIRED_LABELS:
        key = name.lower()
        if key in existing_labels:
            node = existing_labels[key]
            scope = "workspace" if not (node.get("team") or {}).get("id") else "team"
            print(f"  ✅ EXISTS   '{name}'  ({scope}, id={node['id']})")
        elif dry_run:
            print(f"  ⬜ PENDING  '{name}'  (workspace-level, color={color})")
        else:
            # Attempt workspace-level first (requires workspace admin)
            label_id = _create_label(api_key, name, color)
            if label_id:
                print(f"  ✅ CREATED  '{name}'  (workspace, id={label_id})")
            else:
                # Fallback: team-scoped label
                label_id = _create_label(api_key, name, color, team_id=team_id)
                if label_id:
                    print(
                        f"  ✅ CREATED  '{name}'  (team-scoped, id={label_id})\n"
                        f"             Promote to workspace: Settings → Labels → '{name}' → Remove team"
                    )
                else:
                    print(
                        f"  ⚠️  MANUAL  '{name}'\n"
                        f"             UI: Settings → Labels → + New label\n"
                        f"                 Name: {name}  Color: {color}"
                    )
                    label_manual.append(name)

    # ── 3. Custom field (always manual) ───────────────────────────────────────
    print()
    print("=== Custom Field ===")
    print(
        "  ⚠️  MANUAL  'Pi-Dev Run ID'  (not in standard Linear GraphQL API)\n"
        "             UI: Settings → Custom fields → + New field\n"
        "                 Name: Pi-Dev Run ID  |  Type: Text  |  Scope: All issues"
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=== Summary ===")
    if exit_code == 0:
        if label_manual:
            print(
                f"⚠️  Workflow states OK.  {len(label_manual)} label(s) require workspace-admin:"
            )
            for lbl in label_manual:
                print(f"   • {lbl}")
        else:
            print("✅ All automatable items (workflow states + labels) are in place.")
        print(
            "⚠️  Always-manual: create 'Pi-Dev Run ID' custom field in Linear UI\n"
            "   (Settings → Custom fields)."
        )
    else:
        print(
            "❌ One or more workflow states could not be created — see errors above.\n"
            "   If the API key lacks team-admin scope, create states manually:\n"
            "   Linear UI: Settings → Workflows → + New status"
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
