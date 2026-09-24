"""Which lane a self-claimed mesh ticket runs in, and where a plan-lane packet lands.

Two labels feed `/api/mesh/claim/self`:

- ``mesh:auto`` — the build lane. The node makes a worktree and changes code.
- ``idea:plan`` — the plan lane. The node runs a read-only gs-autoplan review and hands
  back one markdown Board packet (``mesh/plan_lane.py``).

A ticket carrying both is ``plan``: an idea is never built before it is reviewed.

The dispatcher assigns no lane, so a dispatched claim runs as build. It therefore
skips any ticket whose labels carry ``idea:plan`` (``mesh_dispatch_service._assign``);
such a ticket reaches a node only through ``/claim/self``. Explicit ``linear_ids`` sent to
``/dispatch`` carry no labels and are dispatched as the operator named them.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel

from . import mesh_fleet, mesh_priority

log = logging.getLogger("pi-ceo.mesh_lanes")

PLAN_LABEL = "idea:plan"
BUILD_LABEL = "mesh:auto"
SELF_CLAIM_QUERY = (
    f'query{{issues(first:50,filter:{{labels:{{name:{{in:["{BUILD_LABEL}","{PLAN_LABEL}"]}}}},'
    'state:{type:{in:["backlog","unstarted"]}}}){nodes{id identifier title '
    'description priority team{id} labels{nodes{name}}}}}'
)
# The idea-pipeline store lives under the repo root, as routes/idea_pipeline.py has it.
REPO_ROOT = Path(__file__).resolve().parents[2]


class PlanPacketFields(BaseModel):
    """What a plan-lane node adds to `/claim/update`. `packet_md` and `title` are
    untrusted ticket-derived text, stored and rendered as text and capped on attach.
    `host` names the caller, which must be the machine holding the claim."""

    packet_md: Optional[str] = None
    title: Optional[str] = None
    host: Optional[str] = None


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
