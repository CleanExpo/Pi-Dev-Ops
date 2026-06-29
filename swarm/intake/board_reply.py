"""BoardReplyTick — the advance-waiting-threads step of the Client Intake
Pipeline. Completes the round-trip that BoardSpmForwarder begins.

The board is async: the forwarder enqueues a deliberation (board.from_margot)
and records an intake_board_rounds row; minutes appear later. This tick polls
each pending round's board session via get_completed; when one has completed
it distills the minutes through spm.aggregate_board_response, delivers the
partner-facing reply, and marks the round replied (or failed).

Pure orchestration over injected collaborators (a pending-round source, a
completion checker, an LLM, a reply sink, a round updater) so it is unit
testable; the concrete Supabase/Telegram adapters are wired separately
(CIP-PR7). Per-round fire-and-forget: one round's failure never blocks others.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from swarm.intake.spm import ProjectContext, SPMBrief, aggregate_board_response

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingRound:
    """A board round awaiting completion, with what aggregation needs."""
    round_id: str
    thread_id: str
    board_session_id: str
    requesting_partner_id: str
    project: ProjectContext
    spm_brief: SPMBrief


@dataclass(frozen=True)
class TickResult:
    processed: int = 0
    replied: int = 0
    pending: int = 0
    failed: int = 0
    errored: int = 0


# completion_checker(session_id) -> board session (with .succeeded(),
# .deliberation_text, .minutes_summary) or None while still deliberating.
CompletionChecker = Callable[[str], Any]


def _default_completion_checker(session_id: str) -> Any:
    from swarm.bots import board
    return board.get_completed(session_id)


class ReplyDelivery:
    def send(self, *, thread_id: str, text: str) -> None: ...


class RoundUpdater:
    def mark_replied(self, *, round_id: str, aggregated_reply: str,
                     next_action: str) -> None: ...

    def mark_failed(self, *, round_id: str, error: str) -> None: ...


class BoardReplyTick:
    def __init__(
        self,
        *,
        pending_rounds: Callable[[], Iterable[PendingRound]],
        llm: Any,
        reply: ReplyDelivery,
        round_updater: RoundUpdater,
        completion_checker: CompletionChecker = _default_completion_checker,
    ) -> None:
        self._pending_rounds = pending_rounds
        self._llm = llm
        self._reply = reply
        self._rounds = round_updater
        self._completed = completion_checker

    def run_once(self) -> TickResult:
        processed = replied = pending = failed = errored = 0
        for r in self._pending_rounds():
            processed += 1
            try:
                session = self._completed(r.board_session_id)
                if session is None:
                    pending += 1
                    continue
                if not session.succeeded():
                    self._rounds.mark_failed(
                        round_id=r.round_id,
                        error=getattr(session, "error", None) or "board deliberation failed",
                    )
                    failed += 1
                    continue

                minutes = session.deliberation_text or session.minutes_summary
                agg = aggregate_board_response(
                    r.project, r.spm_brief, minutes, r.requesting_partner_id,
                    llm=self._llm,
                )
                self._reply.send(thread_id=r.thread_id, text=agg.summary_for_partner)
                self._rounds.mark_replied(
                    round_id=r.round_id,
                    aggregated_reply=agg.summary_for_partner,
                    next_action=agg.next_action,
                )
                replied += 1
            except Exception:  # noqa: BLE001 — per-round fire-and-forget
                log.exception(
                    "BoardReplyTick failed for round=%s session=%s",
                    r.round_id, r.board_session_id,
                )
                errored += 1
        return TickResult(processed=processed, replied=replied, pending=pending,
                          failed=failed, errored=errored)
