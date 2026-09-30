"""Which lane a self-claimed mesh ticket runs in, and where a plan-lane packet lands.

Two labels feed `/api/mesh/claim/self`:

- ``mesh:auto`` — the build lane. The node makes a worktree and changes code.
- ``idea:plan`` — the plan lane. The node runs a read-only gs-autoplan review and hands
  back one markdown Board packet (``mesh/plan_lane.py``).

A ticket carrying both is ``plan``: an idea is never built before it is reviewed.

W1b (audit rank #1): ``pi-dev:autonomous`` also feeds the build lane, in Todo or Ready
for Pi-Dev, when its Linear project is in config/harness/projects.json — the same
``issue_is_claimable`` rule the Railway poller uses. The claim carries the project's
``repo`` so the runner builds in that repository and never in its default one. Every
candidate, whatever its label, must also pass ``claim_refusal`` (no open blocker, no
recent Blocked, no third start in 24h, no blocked-reason label).

The dispatcher assigns no lane, so a dispatched claim runs as build. It therefore
skips any ticket whose labels carry ``idea:plan`` (``mesh_dispatch_service._assign``);
such a ticket reaches a node only through ``/claim/self``. Explicit ``linear_ids`` sent to
``/dispatch`` carry no labels and are dispatched as the operator named them.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel

from . import mesh_fleet, mesh_priority
from .autonomy_eligibility import (
    AUTONOMY_LABEL, GUARD_FIELDS, MESH_STATES, claim_refusal, issue_is_claimable,
    issue_label_names, issue_project_id, registry_repos,
)

log = logging.getLogger("pi-ceo.mesh_lanes")

PLAN_LABEL = "idea:plan"
BUILD_LABEL = "mesh:auto"
_PAGE_ARGS = "first:50"
# Two branches, so the autonomous lane is read by state NAME (Todo / Ready for Pi-Dev)
# and 195 finished pi-dev:autonomous tickets never ride along on every 30s poll.
_STATE_NAMES = ",".join(f'"{n}"' for n in sorted(MESH_STATES))
SELF_CLAIM_QUERY = (
    f'query{{issues({_PAGE_ARGS},filter:{{or:['
    f'{{labels:{{name:{{in:["{BUILD_LABEL}","{PLAN_LABEL}"]}}}},'
    'state:{type:{in:["backlog","unstarted"]}}},'
    f'{{labels:{{name:{{eq:"{AUTONOMY_LABEL}"}}}},state:{{name:{{in:[{_STATE_NAMES}]}}}}}}'
    ']}){pageInfo{hasNextPage endCursor} nodes{id identifier title '
    f'description priority team{{id}} state{{name}} labels{{nodes{{name}}}} {GUARD_FIELDS}}}}}}}'
)
_MAX_PAGES = 20
# The idea-pipeline store lives under the repo root, as routes/idea_pipeline.py has it.
REPO_ROOT = Path(__file__).resolve().parents[2]


class PlanPacketFields(BaseModel):
    """What a plan-lane node adds to `/claim/update`. `packet_md` and `title` are
    untrusted ticket-derived text, stored and rendered as text and capped on attach.
    `host` names the caller, which must be the machine holding the claim."""

    packet_md: Optional[str] = None
    title: Optional[str] = None
    host: Optional[str] = None


def _autonomy_only(issue: dict) -> bool:
    """Admitted only by pi-dev:autonomous — neither mesh:auto nor idea:plan."""
    labels = issue_label_names(issue)
    return AUTONOMY_LABEL in labels and labels.isdisjoint({BUILD_LABEL, PLAN_LABEL})


def needs_repo(issue: dict) -> bool:
    """True for autonomy-lane work, which must be built in its project's repo."""
    return _autonomy_only(issue)


def eligible(issue: dict, repos: dict[str, str]) -> bool:
    """The shared admission rule for a mesh candidate (claim/self and dispatch)."""
    if _autonomy_only(issue):
        return issue_is_claimable(issue, registered_project_ids=set(repos), states=MESH_STATES)
    return claim_refusal(issue) is None


def repo_of(issue: dict, repos: dict[str, str]) -> Optional[str]:
    """owner/name to build in, for a registered project; None means the runner default."""
    return repos.get(issue_project_id(issue) or "")


def candidates(graphql) -> tuple[list[dict], dict[str, str]]:
    """Every eligible open candidate, all pages, plus the project -> repo registry.

    ``graphql`` takes one query string and returns the ``data`` object.
    """
    repos = registry_repos()
    nodes: list[dict] = []
    query = SELF_CLAIM_QUERY
    for _ in range(_MAX_PAGES):
        issues = (graphql(query) or {}).get("issues") or {}
        nodes.extend(issues.get("nodes") or [])
        page = issues.get("pageInfo") or {}
        cursor = page.get("endCursor")
        if not page.get("hasNextPage") or not cursor:
            break
        query = SELF_CLAIM_QUERY.replace(_PAGE_ARGS, f"{_PAGE_ARGS},after:{json.dumps(cursor)}", 1)
    return [n for n in nodes if eligible(n, repos)], repos


def lane_of(issue: dict) -> str:
    """``plan`` when the ticket carries ``idea:plan`` at all, else ``build``."""
    nodes = (issue.get("labels") or {}).get("nodes") or []
    return "plan" if any((n or {}).get("name") == PLAN_LABEL for n in nodes) else "build"


def ranked(nodes: Iterable[dict], open_ids: set) -> list[dict]:
    """Unclaimed tickets, highest Linear priority first, identifier as tie-break."""
    return sorted(
        (n for n in nodes if n.get("identifier") and n["identifier"] not in open_ids),
        key=lambda n: (mesh_priority.priority_rank(n.get("priority")), n["identifier"]),
    )


def _holds_claim(patched_body: str, host: Optional[str]) -> bool:
    """Whether the claim PATCH updated a row, and that row is the caller's.

    Every node holds the same mesh secret, so a 2xx proves nothing: PostgREST answers
    2xx for a filter that matched no row. `return=representation` gives the rows, and
    only a row whose `machine` is the caller proves the caller held this claim.
    """
    rows, problem = mesh_fleet.parse_rows(patched_body)
    return bool(host) and not problem and any(r.get("machine") == host for r in rows)


def attach_packet(linear_id: str, state: str, fields: PlanPacketFields,
                  patched_body: str) -> Optional[str]:
    """Attach a finished plan-lane packet to its idea-pipeline item; return its idea_id.

    Best-effort by design: the claim row has already been released when this runs, and a
    disk error here must not turn that release into a 500 that the runner cannot act on.
    """
    if state != "done" or not (fields.packet_md or "").strip():
        return None
    if not _holds_claim(patched_body, fields.host):
        log.warning("plan packet for %s refused: caller %s does not hold the claim",
                    linear_id, fields.host)
        return None
    from .idea_pipeline.mesh_packet import attach_plan_packet  # noqa: PLC0415
    try:
        packet = attach_plan_packet(REPO_ROOT, linear_id, fields.packet_md or "",
                                    title=fields.title or "")
    except (OSError, ValueError):
        log.warning("plan packet for %s not attached", linear_id, exc_info=True)
        return None
    return str(packet["idea_id"])
