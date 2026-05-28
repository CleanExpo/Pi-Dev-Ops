"""Tests for swarm.intake.cli — orchestrator behavior under stub providers."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Iterable

import pytest

from swarm.inbox.intake_dispatch import IntakeBot
from swarm.intake.cli import (
    TickResult,
    _parse_args,
    run_once,
)
from swarm.intake.margot_router import ProjectSummary, ThreadState


# ============================================================
# Stubs
# ============================================================

class StubRegistry:
    def __init__(self, bots: list[IntakeBot]):
        self._bots = bots

    def list_active_client_intake_bots(self):
        return list(self._bots)


class _AckCounter:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


class StubPoller:
    """Fetches a pre-seeded list of updates per bot.

    `acks` maps bot_id → list[_AckCounter] so tests can assert which
    updates were acked.
    """
    def __init__(self, per_bot_updates: dict[str, list[dict]] | None = None,
                 raise_for: set[str] | None = None):
        self._updates = per_bot_updates or {}
        self._raise_for = raise_for or set()
        self.acks: dict[str, list[_AckCounter]] = {}

    def fetch_updates(self, bot):
        if bot.bot_id in self._raise_for:
            raise RuntimeError(f"simulated fetch failure for {bot.bot_id}")
        out = []
        ack_list = self.acks.setdefault(bot.bot_id, [])
        for upd in self._updates.get(bot.bot_id, []):
            counter = _AckCounter()
            ack_list.append(counter)
            out.append((upd, counter))
        return out


class StubLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, *, system, user, max_tokens=800, temperature=0.2):
        self.calls += 1
        return json.dumps({
            "has_project_name": False, "project_name": None,
            "has_idea": False, "idea": None,
            "is_rename_signal": False, "proposed_new_name": None,
        })


class StubThreadStore:
    def __init__(self):
        self.upserts = 0
        self._next = 0

    def get_thread_for_chat(self, *, bot_id, chat_id):
        return None

    def upsert_thread(self, *, bot_id, chat_id, thread):
        self.upserts += 1
        if thread.thread_id is None:
            self._next += 1
            thread = replace(thread, thread_id=f"t-{self._next}")
        return thread


class StubProjectStore:
    def list_open_projects(self, *, workspace_slug):
        return []

    def create_project(self, *, workspace_slug, name, slug,
                       owner_partner_id, first_idea):
        return ProjectSummary(
            project_id="p-1", name=name, slug=slug,
            owner_partner_id=owner_partner_id, status="open",
        )

    def rename_project(self, *, project_id, new_name, new_slug):
        pass


class StubPersister:
    def __init__(self):
        self.inbounds = 0
        self.outbounds = 0

    def record_inbound(self, **kwargs):
        self.inbounds += 1

    def record_outbound(self, **kwargs):
        self.outbounds += 1


class StubReply:
    def __init__(self):
        self.sent = 0

    def send_reply(self, *, bot_id, chat_id, text):
        self.sent += 1


class StubForwarder:
    def __init__(self):
        self.forwards = 0

    def forward(self, **kwargs):
        self.forwards += 1


# ============================================================
# Helpers
# ============================================================

def _bot(bot_id="b-1", partner_id="phill", authorized=("100",)) -> IntakeBot:
    return IntakeBot(
        bot_id=bot_id, kind="client_intake", partner_id=partner_id,
        workspace_slug="unite-group",
        authorized_chat_ids=tuple(authorized),
        bot_username=f"@{partner_id}IntakeBot",
    )


def _update(chat_id="100", text="Synthex Brand Refresh",
            update_id=1, from_id=1000) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id},
            "from": {"id": from_id},
            "text": text,
        },
    }


def _deps(*, registry, poller):
    return dict(
        registry=registry,
        poller=poller,
        llm=StubLLM(),
        threads=StubThreadStore(),
        projects=StubProjectStore(),
        persister=StubPersister(),
        reply=StubReply(),
        spm_forwarder=StubForwarder(),
    )


# ============================================================
# Tests
# ============================================================

class TestRunOnce:
    def test_zero_bots_zero_work(self):
        registry = StubRegistry([])
        poller = StubPoller()
        result = run_once(**_deps(registry=registry, poller=poller))
        assert result == TickResult(
            bots_polled=0, updates_processed=0,
            updates_handled=0, updates_rejected=0,
            dry_run=False,
        )

    def test_single_bot_single_update_handled_and_acked(self):
        bot = _bot()
        registry = StubRegistry([bot])
        poller = StubPoller({"b-1": [_update()]})
        result = run_once(**_deps(registry=registry, poller=poller))
        assert result.bots_polled == 1
        assert result.updates_processed == 1
        assert result.updates_handled == 1
        assert result.updates_rejected == 0
        # Ack fired exactly once for the handled update
        assert poller.acks["b-1"][0].calls == 1

    def test_rejected_update_does_not_advance_offset(self):
        bot = _bot()
        registry = StubRegistry([bot])
        # update from unauthorized chat_id (999 not in authorized ("100",))
        poller = StubPoller({"b-1": [_update(chat_id="999")]})
        result = run_once(**_deps(registry=registry, poller=poller))
        assert result.updates_processed == 1
        assert result.updates_handled == 0
        assert result.updates_rejected == 1
        # Ack was NOT called
        assert poller.acks["b-1"][0].calls == 0

    def test_multi_bot_isolation_one_failure_does_not_block_others(self):
        bot_a = _bot(bot_id="b-a", partner_id="phill", authorized=("100",))
        bot_b = _bot(bot_id="b-b", partner_id="duncan", authorized=("200",))
        bot_c = _bot(bot_id="b-c", partner_id="toby", authorized=("300",))
        registry = StubRegistry([bot_a, bot_b, bot_c])
        # bot_b's fetch raises, but bot_a and bot_c should still process
        poller = StubPoller(
            per_bot_updates={
                "b-a": [_update(chat_id="100", update_id=1)],
                "b-c": [_update(chat_id="300", update_id=2)],
            },
            raise_for={"b-b"},
        )
        result = run_once(**_deps(registry=registry, poller=poller))
        assert result.bots_polled == 3
        assert result.updates_processed == 2
        assert result.updates_handled == 2
        assert result.bots_errored == ("b-b",)

    def test_dry_run_processes_but_does_not_dispatch_or_ack(self):
        bot = _bot()
        registry = StubRegistry([bot])
        poller = StubPoller({"b-1": [_update(), _update(update_id=2)]})
        deps = _deps(registry=registry, poller=poller)
        result = run_once(**deps, dry_run=True)
        assert result.dry_run is True
        assert result.updates_processed == 2
        assert result.updates_handled == 0
        assert result.updates_rejected == 0
        # No acks, no DB writes
        for counter in poller.acks["b-1"]:
            assert counter.calls == 0
        assert deps["persister"].inbounds == 0
        assert deps["threads"].upserts == 0
        assert deps["reply"].sent == 0

    def test_per_bot_order_preserved(self):
        bot_a = _bot(bot_id="b-a", partner_id="phill", authorized=("100",))
        bot_b = _bot(bot_id="b-b", partner_id="duncan", authorized=("200",))
        registry = StubRegistry([bot_a, bot_b])
        poller = StubPoller({
            "b-a": [_update(chat_id="100", update_id=1)],
            "b-b": [_update(chat_id="200", update_id=2)],
        })
        deps = _deps(registry=registry, poller=poller)
        result = run_once(**deps)
        assert result.bots_polled == 2
        assert result.updates_handled == 2
        # Each bot's update was acked once
        assert poller.acks["b-a"][0].calls == 1
        assert poller.acks["b-b"][0].calls == 1


# ============================================================
# argparse
# ============================================================

class TestParseArgs:
    def test_run_once_default(self):
        args = _parse_args(["run-once"])
        assert args.cmd == "run-once"
        assert args.dry_run is False
        assert args.log_level == "INFO"

    def test_run_once_dry_run_flag(self):
        args = _parse_args(["run-once", "--dry-run"])
        assert args.dry_run is True

    def test_run_once_log_level(self):
        args = _parse_args(["run-once", "--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_unknown_subcommand_exits(self):
        with pytest.raises(SystemExit):
            _parse_args(["bogus"])
