"""Supabase-backed collaborators for BoardReplyTick: the source of board
rounds awaiting completion, and the updater that records the outcome.

Reads intake_board_rounds (+ joins to intake_threads / intake_projects /
intake_messages) to assemble a PendingRound, and PATCHes the round on
completion. Targets the live Pi CEO schema; transport injected for tests.

Tenant scoping: service-role bypasses RLS, so every query is keyed by the
round / thread id explicitly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from swarm.intake.board_reply import PendingRound
from swarm.intake.round_store import _pi_ceo_sb_request
from swarm.intake.spm import SWOT, ProjectContext, SPMBrief

SbRequest = Callable[..., Any]

# Board aggregation next_action -> intake_threads.status (CHECK-constrained).
_NEXT_ACTION_TO_THREAD_STATUS = {
    "awaiting_partner": "awaiting_client",
    "ready_for_production": "ready_for_production",
    "paused_human_review": "paused_human_review",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _spm_brief_from_jsonb(d: dict) -> SPMBrief:
    swot = d.get("swot") or {}
    return SPMBrief(
        layout=d.get("layout", ""), framework=d.get("framework", ""),
        suitability=d.get("suitability", ""),
        swot=SWOT(
            strengths=list(swot.get("strengths") or []),
            weaknesses=list(swot.get("weaknesses") or []),
            opportunities=list(swot.get("opportunities") or []),
            threats=list(swot.get("threats") or []),
        ),
        open_questions=list(d.get("open_questions") or []),
        ready_for_production=bool(d.get("ready_for_production", False)),
        rationale=d.get("rationale", ""),
    )


def _project_from_row(r: dict) -> ProjectContext:
    return ProjectContext(
        project_id=r["id"], workspace_slug=r["workspace_slug"], name=r["name"],
        slug=r["slug"], owner_partner_id=r["owner_partner_id"],
        approval_policy=r.get("approval_policy") or "creator_only",
        description=r.get("description"), status=r.get("status") or "discovery",
        github_repo=r.get("github_repo"),
    )


class SupabasePendingRoundSource:
    def __init__(self, *, sb_request: SbRequest | None = None) -> None:
        self._sb = sb_request or _pi_ceo_sb_request

    def __call__(self) -> Iterable[PendingRound]:
        rounds = self._sb(
            "GET", "/intake_board_rounds",
            params={"status": "in.(requested,deliberating)",
                    "select": "id,thread_id,board_session_id,spm_brief",
                    "order": "created_at"},
        ) or []
        out: list[PendingRound] = []
        for rd in rounds:
            if not rd.get("board_session_id"):
                continue
            threads = self._sb(
                "GET", "/intake_threads",
                params={"id": f"eq.{rd['thread_id']}", "select": "project_id"},
            ) or []
            if not threads or not threads[0].get("project_id"):
                continue
            project_id = threads[0]["project_id"]
            projects = self._sb(
                "GET", "/intake_projects",
                params={"id": f"eq.{project_id}",
                        "select": "id,workspace_slug,name,slug,owner_partner_id,"
                                  "approval_policy,description,status,github_repo"},
            ) or []
            if not projects:
                continue
            project = _project_from_row(projects[0])
            out.append(PendingRound(
                round_id=rd["id"], thread_id=rd["thread_id"],
                board_session_id=rd["board_session_id"],
                requesting_partner_id=self._requesting_partner(rd["thread_id"], project),
                project=project,
                spm_brief=_spm_brief_from_jsonb(rd.get("spm_brief") or {}),
            ))
        return out

    def _requesting_partner(self, thread_id: str, project: ProjectContext) -> str:
        msgs = self._sb(
            "GET", "/intake_messages",
            params={"thread_id": f"eq.{thread_id}", "direction": "eq.inbound",
                    "select": "submitted_by_partner_id",
                    "order": "created_at.desc", "limit": "1"},
        ) or []
        if msgs and msgs[0].get("submitted_by_partner_id"):
            return msgs[0]["submitted_by_partner_id"]
        return project.owner_partner_id


class SupabaseRoundUpdater:
    def __init__(self, *, sb_request: SbRequest | None = None) -> None:
        self._sb = sb_request or _pi_ceo_sb_request

    def mark_replied(self, *, round_id: str, aggregated_reply: str, next_action: str) -> None:
        self._sb(
            "PATCH", "/intake_board_rounds",
            params={"id": f"eq.{round_id}"},
            body={"status": "replied", "aggregated_reply": aggregated_reply,
                  "completed_at": _now_iso()},
            extra_headers={"Prefer": "return=minimal"},
        )
        # Advance the owning thread per the board's recommended next action.
        thread_status = _NEXT_ACTION_TO_THREAD_STATUS.get(next_action)
        if thread_status:
            rows = self._sb(
                "GET", "/intake_board_rounds",
                params={"id": f"eq.{round_id}", "select": "thread_id"},
            ) or []
            if rows:
                self._sb(
                    "PATCH", "/intake_threads",
                    params={"id": f"eq.{rows[0]['thread_id']}"},
                    body={"status": thread_status, "updated_at": _now_iso()},
                    extra_headers={"Prefer": "return=minimal"},
                )

    def mark_failed(self, *, round_id: str, error: str) -> None:
        # intake_board_rounds has no error column (live schema); status only.
        self._sb(
            "PATCH", "/intake_board_rounds",
            params={"id": f"eq.{round_id}"},
            body={"status": "failed", "completed_at": _now_iso()},
            extra_headers={"Prefer": "return=minimal"},
        )
