"""Client-Intake Pipeline CLI — `python -m swarm.intake.cli run-once`.

Pure-logic orchestrator (run_once) plus a thin argparse shell so
Hermes cron can invoke it every minute. All side effects pushed
behind Protocols so run_once is fully unit-testable.

Concrete providers (DB-backed ThreadStore / ProjectStore /
MessagePersister / ReplyDelivery / SpmForwarder / IntakeBotRegistry
and the Telegram poller) land in PR7 alongside Duncan + Toby bot
provisioning. PR6 covers only the orchestrator + tests + the
argparse entry point.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol

from swarm.inbox.intake_dispatch import (
    IntakeBot,
    LLMClient,
    MessagePersister,
    ProjectStore,
    ReplyDelivery,
    SpmForwarder,
    ThreadStore,
    dispatch_telegram_update,
)

log = logging.getLogger("swarm.intake.cli")


# ============================================================
# Providers
# ============================================================

class IntakeBotRegistry(Protocol):
    """Lists the bots the CLI should poll.

    Only bots with `kind='client_intake'` and `status='active'` should
    be returned; the registry handles that filter (no need for the
    orchestrator to know about table schemas).
    """
    def list_active_client_intake_bots(self) -> Iterable[IntakeBot]: ...


class TelegramPoller(Protocol):
    """Long-poll updates for one bot, advance its long_poll_offset
    as the orchestrator successfully dispatches each update.

    `fetch_updates` returns (update_dict, ack) tuples where calling
    `ack()` after a successful dispatch persists
    `intake_client_bots.long_poll_offset = update_id + 1`.
    """
    def fetch_updates(self, bot: IntakeBot) -> Iterable[tuple[dict, "OffsetAck"]]: ...


class OffsetAck(Protocol):
    def __call__(self) -> None: ...


# ============================================================
# Result type
# ============================================================

@dataclass(frozen=True)
class TickResult:
    bots_polled: int
    updates_processed: int
    updates_handled: int
    updates_rejected: int
    bots_errored: tuple[str, ...] = field(default=())
    dry_run: bool = False


# ============================================================
# Orchestrator (pure — all I/O behind Protocols)
# ============================================================

def run_once(
    *,
    registry: IntakeBotRegistry,
    poller: TelegramPoller,
    llm: LLMClient,
    threads: ThreadStore,
    projects: ProjectStore,
    persister: MessagePersister,
    reply: ReplyDelivery,
    spm_forwarder: SpmForwarder,
    dry_run: bool = False,
    now: datetime | None = None,
) -> TickResult:
    """One CIP poll cycle.

    For each active client_intake bot:
      * fetch any new Telegram updates
      * dispatch_telegram_update for each
      * ack offset only on successful dispatch
      * any per-bot exception is logged + recorded; other bots
        continue (fire-and-forget per bot).
    """
    now = now or datetime.now(timezone.utc)
    bots = list(registry.list_active_client_intake_bots())
    processed = 0
    handled = 0
    rejected = 0
    errored: list[str] = []

    for bot in bots:
        try:
            for update, ack in poller.fetch_updates(bot):
                processed += 1
                if dry_run:
                    continue
                outcome = dispatch_telegram_update(
                    update, bot,
                    llm=llm,
                    threads=threads,
                    projects=projects,
                    persister=persister,
                    reply=reply,
                    spm_forwarder=spm_forwarder,
                    now=now,
                )
                if outcome.handled:
                    handled += 1
                    ack()  # only advance offset on success
                else:
                    rejected += 1
                    # Do NOT ack — leave the offset where it is so a
                    # buggy update can be re-investigated. The rejected
                    # case represents either malformed input or a
                    # G3 trust failure; both are observable on the
                    # next tick if not handled out-of-band.
                    log.warning(
                        "intake update rejected bot=%s reason=%s",
                        bot.bot_id, outcome.rejected_reason,
                    )
        except Exception as exc:  # noqa: BLE001 — one bot's failure
            #                                       must not block others
            log.exception("intake bot tick failed bot=%s: %s", bot.bot_id, exc)
            errored.append(bot.bot_id)
            continue

    return TickResult(
        bots_polled=len(bots),
        updates_processed=processed,
        updates_handled=handled,
        updates_rejected=rejected,
        bots_errored=tuple(errored),
        dry_run=dry_run,
    )


# ============================================================
# Provider construction — DEFERRED to PR7
# ============================================================

def _build_default_providers():
    """Construct the real DB / Telegram / LLM providers.

    Concrete implementations land in PR7 (alongside Duncan + Toby
    provisioning). Until then, this raises so CLI invocation fails
    loudly rather than silently no-op.
    """
    raise NotImplementedError(
        "swarm.intake.cli: default providers not wired yet (CIP-PR7). "
        "Run-once is invokable in tests by passing explicit providers."
    )


# ============================================================
# argparse entry point
# ============================================================

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="swarm.intake.cli",
        description="Client Intake Pipeline — Telegram → Margot → SPM → Board",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    once = sub.add_parser(
        "run-once",
        help="Poll every active client_intake bot once. Intended for cron.",
    )
    once.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch updates but don't dispatch / advance offsets.",
    )
    once.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.cmd == "run-once":
        providers = _build_default_providers()
        result = run_once(**providers, dry_run=args.dry_run)
        log.info(
            "tick complete bots=%d processed=%d handled=%d rejected=%d errored=%d",
            result.bots_polled, result.updates_processed,
            result.updates_handled, result.updates_rejected,
            len(result.bots_errored),
        )
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
