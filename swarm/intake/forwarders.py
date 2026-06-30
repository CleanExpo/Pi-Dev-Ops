"""Concrete `SpmForwarder` — the production executor for the
`forward_to_spm` hand-off in the Client Intake Pipeline.

It turns a landed partner message into an SPM brief and an enqueued Board
deliberation, then records the round. Per the async board model
(`board.from_margot` -> `request_deliberation` enqueues and returns an id),
the partner-facing reply is produced LATER, on the advance-waiting-threads
tick — NOT here. `forward()` is fire-and-forget by the SpmForwarder Protocol
contract: it must never raise into the dispatcher.

Reuses `spm.build_spm_brief` and `board.from_margot`; adds no new pipeline
logic. Wired in behind a default-OFF flag (`INTAKE_BOARD_FANOUT`) and the
TAO kill-switch so first activation is deliberate and spend is bounded.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Iterable, Protocol

from swarm.intake.spm import (
    LLMClient,
    ProjectContext,
    SPMBrief,
    ThreadMessage,
    build_spm_brief,
)

log = logging.getLogger(__name__)


# ── Collaborator Protocols (concrete adapters injected at wiring time) ────────
class ProjectLoader(Protocol):
    def load_project(self, *, project_id: str) -> ProjectContext: ...


class MessageLoader(Protocol):
    def recent_messages(
        self, *, thread_id: str, limit: int = 30
    ) -> Iterable[ThreadMessage]: ...


class BoardRoundStore(Protocol):
    """Persists one `intake_board_rounds` row per enqueued deliberation."""
    def record_round(
        self, *, thread_id: str, project_id: str, bot_id: str,
        board_id: str, brief: SPMBrief,
    ) -> None: ...


# board_submit signature: keyword-only, returns the board/queue id.
BoardSubmit = Callable[..., str]


def fanout_enabled() -> bool:
    """Default-OFF gate. Flip with INTAKE_BOARD_FANOUT=1."""
    return os.environ.get("INTAKE_BOARD_FANOUT", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _default_board_submit(*, topic: str, insight: str,
                          requested_decisions: list[str] | None) -> str:
    from swarm.bots import board
    return board.from_margot(
        topic=topic, insight=insight, requested_decisions=requested_decisions,
    )


def _default_kill_switch() -> bool:
    from swarm import kill_switch
    return kill_switch.is_active()


def _render_brief(brief: SPMBrief) -> str:
    """Render the SPM assessment as the board's material_input.

    The Board deliberates on the SPM's structured assessment, not the raw
    client message (SPEC: Telegram -> Margot -> SPM -> Board).
    """
    swot = brief.swot
    return (
        f"Layout: {brief.layout}\n"
        f"Framework: {brief.framework}\n"
        f"Suitability: {brief.suitability}\n"
        f"Strengths: {', '.join(swot.strengths) or '—'}\n"
        f"Weaknesses: {', '.join(swot.weaknesses) or '—'}\n"
        f"Opportunities: {', '.join(swot.opportunities) or '—'}\n"
        f"Threats: {', '.join(swot.threats) or '—'}\n"
        f"Open questions: {', '.join(brief.open_questions) or '—'}\n"
        f"Ready for production: {brief.ready_for_production}\n"
        f"Rationale: {brief.rationale}"
    )


class BoardSpmForwarder:
    """SpmForwarder implementation: brief -> enqueue board round -> persist."""

    def __init__(
        self,
        *,
        project_loader: ProjectLoader,
        message_loader: MessageLoader,
        round_store: BoardRoundStore,
        llm: LLMClient,
        board_submit: BoardSubmit = _default_board_submit,
        kill_switch: Callable[[], bool] = _default_kill_switch,
        enabled: Callable[[], bool] = fanout_enabled,
        should_skip_debounce: Callable[[str], bool] = lambda thread_id: False,
    ) -> None:
        self._projects = project_loader
        self._messages = message_loader
        self._rounds = round_store
        self._llm = llm
        self._board_submit = board_submit
        self._kill_switch = kill_switch
        self._enabled = enabled
        self._should_skip_debounce = should_skip_debounce

    def forward(
        self, *, thread_id: str, project_id: str, bot_id: str, body: str,
    ) -> None:
        try:
            if not self._enabled():
                return
            if self._kill_switch():
                log.warning(
                    "intake board fan-out skipped: kill-switch active "
                    "(thread=%s project=%s)", thread_id, project_id,
                )
                return
            if self._should_skip_debounce(thread_id):
                log.info(
                    "intake board fan-out debounced (thread=%s)", thread_id,
                )
                return

            project = self._projects.load_project(project_id=project_id)
            messages = self._messages.recent_messages(thread_id=thread_id)
            brief = build_spm_brief(project, messages, llm=self._llm)

            board_id = self._board_submit(
                topic=project.name,
                insight=_render_brief(brief),
                requested_decisions=brief.open_questions or None,
            )

            self._rounds.record_round(
                thread_id=thread_id, project_id=project_id, bot_id=bot_id,
                board_id=board_id, brief=brief,
            )
        except Exception:  # noqa: BLE001 — fire-and-forget per Protocol
            log.exception(
                "BoardSpmForwarder.forward failed (thread=%s project=%s)",
                thread_id, project_id,
            )
