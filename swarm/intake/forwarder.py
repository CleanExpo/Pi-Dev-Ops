"""swarm/intake/forwarder.py — concrete production SpmForwarder.

Closes the gap diagnosed in RA-6671: a project landing on an intake bot
must be handed off to the Board for deliberation ("bring it back to the
board for discussion"). Until now the only `SpmForwarder` implementations
were test stubs, so `dispatch_telegram_update`'s `forward_to_spm` action
had nowhere to land.

`ProductionSpmForwarder` implements the `SpmForwarder` Protocol from
`swarm.inbox.intake_dispatch`. On `forward(...)` it assembles a
`BoardBrief` from the landed project and submits it for deliberation via
an injected `submit_to_board` callable (default: the real Board entry
point in `swarm.bots.board`).

Fire-and-forget by contract: any exception is caught and logged so one
bad hand-off never crashes the intake tick. The injected callable keeps
the class unit-testable without touching the Board SDK / filesystem.
"""
from __future__ import annotations

import logging
from typing import Callable, Protocol

log = logging.getLogger("swarm.intake.forwarder")

# Signature of the board-submit seam. Returns a Board session id.
SubmitToBoard = Callable[..., str]


class _SupportsForward(Protocol):
    def forward(
        self, *, thread_id: str, project_id: str, bot_id: str, body: str,
    ) -> None: ...


def _default_submit_to_board(
    *, topic: str, material: str, requested_decisions: list[str],
) -> str:
    """Adapter onto the real Board entry point.

    Imported lazily so unit tests never trigger the Board SDK import
    chain. Routed through `from_margot` because an intake hand-off is a
    research-style insight the Board deliberates on, not a senior-bot
    escalation or a direct founder prompt.
    """
    from swarm.bots import board

    return board.from_margot(
        topic=topic,
        insight=material,
        requested_decisions=requested_decisions,
    )


# Decisions the Board is asked to return for every landed intake project.
_INTAKE_DECISIONS = [
    "Is this project a fit for the portfolio, and which specialist owns it?",
    "What is the recommended first deliverable and framework?",
    "What open questions must the partner answer before production?",
]


class ProductionSpmForwarder:
    """Hand a landed intake project off to the Board for deliberation.

    Args:
        submit_to_board: seam onto the Board. Defaults to the real
            `swarm.bots.board.from_margot`. Tests inject a recorder.
        decisions: the questions put to the Board (override per workspace
            if needed; defaults to the standard intake triad).
    """

    def __init__(
        self,
        *,
        submit_to_board: SubmitToBoard | None = None,
        decisions: list[str] | None = None,
    ) -> None:
        self._submit = submit_to_board or _default_submit_to_board
        self._decisions = list(decisions or _INTAKE_DECISIONS)

    def forward(
        self, *, thread_id: str, project_id: str, bot_id: str, body: str,
    ) -> None:
        """Submit the landed project to the Board. Never raises."""
        topic = self._topic(project_id=project_id, body=body)
        material = self._material(
            thread_id=thread_id, project_id=project_id, bot_id=bot_id, body=body,
        )
        try:
            session_id = self._submit(
                topic=topic,
                material=material,
                requested_decisions=self._decisions,
            )
        except Exception as exc:  # noqa: BLE001 — fire-and-forget hand-off
            log.exception(
                "board hand-off failed project=%s bot=%s: %s",
                project_id, bot_id, exc,
            )
            return
        log.info(
            "board hand-off ok project=%s bot=%s thread=%s session=%s",
            project_id, bot_id, thread_id, session_id,
        )

    @staticmethod
    def _topic(*, project_id: str, body: str) -> str:
        head = " ".join((body or "").split())[:80].strip()
        if head:
            return f"Intake project {project_id}: {head}"
        return f"Intake project {project_id}"

    @staticmethod
    def _material(
        *, thread_id: str, project_id: str, bot_id: str, body: str,
    ) -> str:
        return (
            f"A project landed via intake bot `{bot_id}` and is ready for the "
            f"Board to deliberate on (thread `{thread_id}`, project "
            f"`{project_id}`).\n\n"
            f"Partner's latest message:\n{body or '(no message body)'}"
        )
