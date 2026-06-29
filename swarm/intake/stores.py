"""Supabase-backed CIP data-plane adapters (the run_once providers, minus the
Telegram poller/reply which are a separately-gated slice).

Implements IntakeBotRegistry, ThreadStore, ProjectStore, MessagePersister
against the live Pi CEO `intake_*` tables (schema verified 2026-06-29).

Security (live-verified):
  * The service-role key bypasses RLS, so isolation is NOT enforced by the DB —
    every query is explicitly scoped by client_bot_id / workspace_slug.
  * Bot tokens are stored as env-var NAMES (intake_client_bots.bot_token_env_name),
    never as secrets here; this module never reads or logs a token value.
  * submitted_by_partner_id is persisted as given (trust-derived upstream per
    SPEC G3) — partner identity is never parsed from the message body.

Transport is injected (default _pi_ceo_sb_request) so adapters are unit-testable
without a live DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Literal
from uuid import uuid4

from swarm.inbox.intake_dispatch import IntakeBot
from swarm.intake.margot_router import ProjectSummary, ThreadState
from swarm.intake.round_store import _pi_ceo_sb_request

SbRequest = Callable[..., Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class _Base:
    def __init__(self, *, sb_request: SbRequest | None = None,
                 id_factory: Callable[[str], str] | None = None) -> None:
        self._sb: SbRequest = sb_request or _pi_ceo_sb_request
        self._id = id_factory or _new_id
        self._tenant_cache: dict[str, tuple[str, str]] = {}

    def _bot_tenant(self, bot_id: str) -> tuple[str, str]:
        """(client_slug, workspace_slug) for a bot — needed for NOT NULL cols
        the Protocol signatures don't carry. Cached per instance."""
        if bot_id not in self._tenant_cache:
            rows = self._sb(
                "GET", "/intake_client_bots",
                params={"id": f"eq.{bot_id}", "select": "client_slug,workspace_slug"},
            ) or []
            if not rows:
                raise ValueError(f"intake_client_bots row not found for bot_id={bot_id}")
            self._tenant_cache[bot_id] = (rows[0]["client_slug"], rows[0]["workspace_slug"])
        return self._tenant_cache[bot_id]


class SupabaseIntakeBotRegistry(_Base):
    def list_active_client_intake_bots(self) -> Iterable[IntakeBot]:
        rows = self._sb(
            "GET", "/intake_client_bots",
            params={"status": "eq.active",
                    "select": "id,partner_id,workspace_slug,authorized_chat_ids,bot_username",
                    "order": "created_at"},
        ) or []
        return [
            IntakeBot(
                bot_id=r["id"],
                kind="client_intake",
                partner_id=r.get("partner_id") or "",
                workspace_slug=r["workspace_slug"],
                authorized_chat_ids=tuple(str(c) for c in (r.get("authorized_chat_ids") or [])),
                bot_username=r["bot_username"],
            )
            for r in rows
        ]


class SupabaseThreadStore(_Base):
    def get_thread_for_chat(self, *, bot_id: str, chat_id: str) -> ThreadState | None:
        rows = self._sb(
            "GET", "/intake_threads",
            params={"client_bot_id": f"eq.{bot_id}", "chat_id": f"eq.{chat_id}",
                    "select": "id,project_id,margot_state,status,last_message_at",
                    "limit": "1"},
        ) or []
        if not rows:
            return None
        r = rows[0]
        return ThreadState(
            thread_id=r["id"],
            project_id=r.get("project_id"),
            margot_state=r["margot_state"],
            project_status=r.get("status") or "open",
            last_inbound_at=r.get("last_message_at"),
        )

    def upsert_thread(self, *, bot_id: str, chat_id: str, thread: ThreadState) -> ThreadState:
        client_slug, workspace_slug = self._bot_tenant(bot_id)
        if thread.thread_id:
            self._sb(
                "PATCH", "/intake_threads",
                params={"id": f"eq.{thread.thread_id}"},
                body={
                    "status": thread.project_status,
                    "margot_state": thread.margot_state,
                    "project_id": thread.project_id,
                    "last_message_at": thread.last_inbound_at or _now_iso(),
                    "updated_at": _now_iso(),
                },
                extra_headers={"Prefer": "return=minimal"},
            )
            return thread
        new_id = self._id("it")
        self._sb(
            "POST", "/intake_threads",
            body={
                "id": new_id,
                "client_bot_id": bot_id,
                "client_slug": client_slug,
                "workspace_slug": workspace_slug,
                "chat_id": chat_id,
                "status": thread.project_status,
                "margot_state": thread.margot_state,
                "project_id": thread.project_id,
                "last_message_at": thread.last_inbound_at or _now_iso(),
            },
            extra_headers={"Prefer": "return=minimal"},
        )
        return ThreadState(
            thread_id=new_id, project_id=thread.project_id, margot_state=thread.margot_state,
            project_status=thread.project_status, last_inbound_at=thread.last_inbound_at,
        )


class SupabaseProjectStore(_Base):
    def list_open_projects(self, *, workspace_slug: str) -> Iterable[ProjectSummary]:
        rows = self._sb(
            "GET", "/intake_projects",
            params={"workspace_slug": f"eq.{workspace_slug}", "status": "eq.open",
                    "select": "id,name,slug,owner_partner_id,status"},
        ) or []
        return [
            ProjectSummary(project_id=r["id"], name=r["name"], slug=r["slug"],
                           owner_partner_id=r["owner_partner_id"], status=r.get("status") or "open")
            for r in rows
        ]

    def create_project(self, *, workspace_slug: str, name: str, slug: str,
                       owner_partner_id: str, first_idea: str) -> ProjectSummary:
        new_id = self._id("ip")
        self._sb(
            "POST", "/intake_projects",
            body={
                "id": new_id, "workspace_slug": workspace_slug, "name": name, "slug": slug,
                "owner_partner_id": owner_partner_id, "status": "open",
                "approval_policy": "creator_only", "description": first_idea,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
        return ProjectSummary(project_id=new_id, name=name, slug=slug,
                              owner_partner_id=owner_partner_id, status="open")

    def rename_project(self, *, project_id: str, new_name: str, new_slug: str) -> None:
        self._sb(
            "PATCH", "/intake_projects",
            params={"id": f"eq.{project_id}"},
            body={"name": new_name, "slug": new_slug, "updated_at": _now_iso()},
            extra_headers={"Prefer": "return=minimal"},
        )


class SupabaseMessagePersister(_Base):
    def record_inbound(self, *, bot_id: str, thread_id: str | None, chat_id: str,
                       body: str, submitted_by_partner_id: str,
                       telegram_message_id: int | None, telegram_update_id: int) -> None:
        client_slug, workspace_slug = self._bot_tenant(bot_id)
        # Plain insert: intake_messages has no unique on telegram_update_id
        # (live schema — PK on id only), so dedup stays upstream (dispatcher).
        self._sb(
            "POST", "/intake_messages",
            body={
                "id": self._id("im"), "thread_id": thread_id, "client_slug": client_slug,
                "workspace_slug": workspace_slug, "direction": "inbound", "author": "client",
                "body": body, "submitted_by_partner_id": submitted_by_partner_id,
                "telegram_message_id": telegram_message_id,
                "telegram_update_id": telegram_update_id,
            },
            extra_headers={"Prefer": "return=minimal"},
        )

    def record_outbound(self, *, bot_id: str, thread_id: str | None, chat_id: str,
                        body: str,
                        author: Literal["margot", "spm", "board-summary", "system"]) -> None:
        client_slug, workspace_slug = self._bot_tenant(bot_id)
        self._sb(
            "POST", "/intake_messages",
            body={
                "id": self._id("im"), "thread_id": thread_id, "client_slug": client_slug,
                "workspace_slug": workspace_slug, "direction": "outbound", "author": author,
                "body": body,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
