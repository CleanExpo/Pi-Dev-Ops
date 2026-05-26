"""Client-intake dispatcher — turns a Telegram update into a side-effect plan.

This module is the wiring layer between the existing
`swarm/inbox/intake_router.py` (which long-polls Telegram and persists
raw messages) and the CIP-PR3 margot_router (state machine + LLM).
All I/O is behind Protocols so the dispatcher is fully unit-testable.

For bots with `kind='client_intake'` the existing `intake_router.tick`
calls `dispatch_telegram_update(...)` for each new Update. The
default Linear/wiki/auto-reply path is skipped.

Trust chain (per SPEC §G3):

    raw Telegram Update
        → trusted_partner_id_for_inbound (spm.py)
        → reject if untrusted
        → InboundMessage carries submitted_by_partner_id from
          intake_client_bots.partner_id, not message body

State machine + non-happy-paths (per SPEC §G6) live in margot_router.
This dispatcher just wires the persistence side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable, Literal, Protocol

from swarm.intake.margot_router import (
    InboundMessage,
    LLMClient,
    MargotState,
    ProjectSummary,
    RouterDecision,
    ThreadState,
    route_inbound,
)
from swarm.intake.spm import (
    trusted_partner_id_for_inbound,
)


# ============================================================
# Data shapes
# ============================================================

@dataclass(frozen=True)
class IntakeBot:
    """Subset of intake_client_bots needed to dispatch one update."""
    bot_id: str
    kind: Literal["client_intake", "context"]
    partner_id: str
    workspace_slug: str
    authorized_chat_ids: tuple[str, ...]
    bot_username: str
    chat_id_to_thread_map_key: str = "chat_id"  # for future multi-thread-per-chat


@dataclass(frozen=True)
class DispatchOutcome:
    """What the dispatcher did with one update — used by tests + telemetry."""
    handled: bool
    rejected_reason: str | None = None
    partner_id: str | None = None
    decision: RouterDecision | None = None
    project_id: str | None = None
    thread_id: str | None = None


# ============================================================
# Storage Protocols (concrete adapters in PR6 / PR7)
# ============================================================

class ThreadStore(Protocol):
    def get_thread_for_chat(
        self, *, bot_id: str, chat_id: str,
    ) -> ThreadState | None: ...

    def upsert_thread(
        self,
        *,
        bot_id: str,
        chat_id: str,
        thread: ThreadState,
    ) -> ThreadState: ...


class ProjectStore(Protocol):
    def list_open_projects(
        self, *, workspace_slug: str,
    ) -> Iterable[ProjectSummary]: ...

    def create_project(
        self,
        *,
        workspace_slug: str,
        name: str,
        slug: str,
        owner_partner_id: str,
        first_idea: str,
    ) -> ProjectSummary: ...

    def rename_project(
        self,
        *,
        project_id: str,
        new_name: str,
        new_slug: str,
    ) -> None: ...


class MessagePersister(Protocol):
    def record_inbound(
        self,
        *,
        bot_id: str,
        thread_id: str | None,
        chat_id: str,
        body: str,
        submitted_by_partner_id: str,
        telegram_message_id: int | None,
        telegram_update_id: int,
    ) -> None: ...

    def record_outbound(
        self,
        *,
        bot_id: str,
        thread_id: str | None,
        chat_id: str,
        body: str,
        author: Literal["margot", "spm", "board-summary", "system"],
    ) -> None: ...


class ReplyDelivery(Protocol):
    def send_reply(self, *, bot_id: str, chat_id: str, text: str) -> None: ...


class SpmForwarder(Protocol):
    """Hand-off into the SPM/board pipeline. Async-fire-and-forget in
    production; tests just record the call."""
    def forward(
        self,
        *,
        thread_id: str,
        project_id: str,
        bot_id: str,
        body: str,
    ) -> None: ...


# ============================================================
# Helpers
# ============================================================

def _extract_message_fields(update: dict) -> tuple[str, str, int | None, int]:
    """Return (chat_id, body, telegram_message_id, telegram_update_id).

    Raises KeyError / TypeError if the update is malformed — callers
    should catch and skip rather than crash the tick.
    """
    msg = update["message"]
    chat_id = str(msg["chat"]["id"])
    body = (msg.get("text") or "").strip()
    telegram_message_id = msg.get("message_id")
    telegram_update_id = update["update_id"]
    return chat_id, body, telegram_message_id, telegram_update_id


def _from_user_id(update: dict) -> int | None:
    msg = update.get("message") or {}
    user = msg.get("from") or {}
    user_id = user.get("id")
    return int(user_id) if user_id is not None else None


# ============================================================
# Main dispatcher entry point
# ============================================================

def dispatch_telegram_update(
    update: dict,
    bot: IntakeBot,
    *,
    llm: LLMClient,
    threads: ThreadStore,
    projects: ProjectStore,
    persister: MessagePersister,
    reply: ReplyDelivery,
    spm_forwarder: SpmForwarder,
    partner_telegram_user_id: int | None = None,
    now: datetime | None = None,
) -> DispatchOutcome:
    """Process ONE Telegram update for a client_intake bot.

    Steps:
      1. Extract message fields (skip on malformed update).
      2. G3 anti-spoofing → `trusted_partner_id_for_inbound`.
      3. Load (or create empty) ThreadState for this chat.
      4. Call `route_inbound` to get the RouterDecision.
      5. Execute side effects per `decision.action`.
      6. Persist updated thread state.
    """
    now = now or datetime.now(timezone.utc)

    # ── (1) Extract ────────────────────────────────────────────────
    try:
        chat_id, body, telegram_message_id, telegram_update_id = (
            _extract_message_fields(update)
        )
    except (KeyError, TypeError):
        return DispatchOutcome(handled=False, rejected_reason="malformed_update")

    # ── (2) G3 trust check ─────────────────────────────────────────
    trusted_partner_id, denial = trusted_partner_id_for_inbound(
        bot_partner_id=bot.partner_id,
        telegram_chat_id=chat_id,
        authorized_chat_ids=list(bot.authorized_chat_ids),
        telegram_from_user_id=_from_user_id(update),
        partner_telegram_user_id=partner_telegram_user_id,
    )
    if not trusted_partner_id:
        return DispatchOutcome(
            handled=False,
            rejected_reason=denial or "untrusted_inbound",
        )

    # ── (3) Load thread ────────────────────────────────────────────
    thread = threads.get_thread_for_chat(bot_id=bot.bot_id, chat_id=chat_id)
    if thread is None:
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
            last_inbound_at=now.isoformat(),
        )

    # ── (4) Record inbound + route ─────────────────────────────────
    persister.record_inbound(
        bot_id=bot.bot_id,
        thread_id=thread.thread_id,
        chat_id=chat_id,
        body=body,
        submitted_by_partner_id=trusted_partner_id,
        telegram_message_id=telegram_message_id,
        telegram_update_id=telegram_update_id,
    )

    inbound = InboundMessage(
        chat_id=chat_id,
        body=body,
        submitted_by_partner_id=trusted_partner_id,
        telegram_user_id=_from_user_id(update),
        created_at=now.isoformat(),
    )

    open_projects = list(projects.list_open_projects(workspace_slug=bot.workspace_slug))

    decision = route_inbound(
        inbound, thread, open_projects, llm=llm, now=now,
    )

    # ── (5) Execute side effects (excluding SPM forward, which
    # needs the persisted thread_id) ───────────────────────────────
    new_thread, pending_forward_body = _apply_decision(
        decision, thread,
        bot=bot,
        chat_id=chat_id,
        trusted_partner_id=trusted_partner_id,
        projects=projects,
        persister=persister,
        reply=reply,
        body=body,
        now=now,
    )

    # ── (6) Persist updated thread ─────────────────────────────────
    persisted = threads.upsert_thread(
        bot_id=bot.bot_id, chat_id=chat_id, thread=new_thread,
    )

    # ── (7) SPM forward — now that we have a thread_id ─────────────
    if pending_forward_body is not None and persisted.thread_id and persisted.project_id:
        spm_forwarder.forward(
            thread_id=persisted.thread_id,
            project_id=persisted.project_id,
            bot_id=bot.bot_id,
            body=pending_forward_body,
        )

    return DispatchOutcome(
        handled=True,
        partner_id=trusted_partner_id,
        decision=decision,
        project_id=persisted.project_id,
        thread_id=persisted.thread_id,
    )


# ============================================================
# Decision → side-effects translator
# ============================================================

def _send_and_record_reply(
    *,
    bot: IntakeBot,
    chat_id: str,
    thread_id: str | None,
    text: str,
    persister: MessagePersister,
    reply: ReplyDelivery,
    author: Literal["margot", "spm", "board-summary", "system"] = "margot",
) -> None:
    if not text:
        return
    reply.send_reply(bot_id=bot.bot_id, chat_id=chat_id, text=text)
    persister.record_outbound(
        bot_id=bot.bot_id,
        thread_id=thread_id,
        chat_id=chat_id,
        body=text,
        author=author,
    )


def _apply_decision(
    decision: RouterDecision,
    thread: ThreadState,
    *,
    bot: IntakeBot,
    chat_id: str,
    trusted_partner_id: str,
    projects: ProjectStore,
    persister: MessagePersister,
    reply: ReplyDelivery,
    body: str,
    now: datetime,
) -> tuple[ThreadState, str | None]:
    """Turn a RouterDecision into concrete writes.

    Returns `(new_thread, pending_forward_body)`. If the caller should
    invoke the SPM forwarder AFTER persisting the thread (so the
    forwarder gets a real `thread_id`), `pending_forward_body` is the
    body to forward; else it's None.
    """
    action = decision.action
    new_thread = replace(
        thread,
        margot_state=decision.next_state,
        last_inbound_at=now.isoformat(),
    )
    pending_forward_body: str | None = None

    # Always send the reply text if present (except forward_to_spm —
    # which is silent because SPM/board reply will follow asynchronously)
    if decision.reply_text and action != "forward_to_spm":
        _send_and_record_reply(
            bot=bot, chat_id=chat_id, thread_id=thread.thread_id,
            text=decision.reply_text, persister=persister, reply=reply,
        )

    if action == "advance_to_idea":
        new_thread = replace(
            new_thread,
            candidate_name=decision.captured_project_name,
            candidate_slug=decision.captured_project_slug,
        )

    elif action == "create_project":
        first_idea = decision.metadata.get("first_idea", body)
        created = projects.create_project(
            workspace_slug=bot.workspace_slug,
            name=decision.captured_project_name or "",
            slug=decision.captured_project_slug or "",
            owner_partner_id=trusted_partner_id,
            first_idea=first_idea,
        )
        new_thread = replace(
            new_thread,
            project_id=created.project_id,
            project_name=created.name,
            project_owner_partner_id=created.owner_partner_id,
            candidate_name=None,
            candidate_slug=None,
        )
        pending_forward_body = first_idea

    elif action == "rename_project":
        if thread.project_id and decision.rename_to and decision.captured_project_slug:
            projects.rename_project(
                project_id=thread.project_id,
                new_name=decision.rename_to,
                new_slug=decision.captured_project_slug,
            )
            new_thread = replace(new_thread, project_name=decision.rename_to)

    elif action == "forward_to_spm":
        pending_forward_body = decision.metadata.get("forwarded_body", body)

    # `reject`, `reply`, `surface_duplicate`, `confirm_resume`,
    # `pause_for_review`, `noop` — reply already sent above; no DB writes.

    return new_thread, pending_forward_body
