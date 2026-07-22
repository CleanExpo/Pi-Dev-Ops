"""Bounded in-memory ledger seam used by deterministic watcher fixtures."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from swarm.ccw_support_contract import ERROR_CODES
from .source import SourceItem


def stable_source_key(provider_id: str) -> str:
    if not provider_id:
        raise ValueError("MISSING_SOURCE_ID")
    return hashlib.sha256(provider_id.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HealthRun:
    run_id: str
    started_at: datetime
    heartbeat_at: datetime
    completed_at: datetime | None = None
    outcome: str = "running"
    source_auth_ok: bool | None = None
    source_query_ok: bool | None = None
    source_seen_count: int = 0
    persisted_count: int = 0
    pending_count: int = 0
    response_matched_count: int = 0
    cursor_hash: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class Ticket:
    source_key: str
    received_at: datetime
    priority: str
    first_response_at: datetime | None = None


@dataclass(frozen=True)
class AlertIntent:
    intent_id: str
    dedup_key: str
    state: str
    source_run_id: str
    opened_at: datetime
    last_seen_at: datetime
    status: str = "pending"


class InMemoryLedger:
    """Small storage port proving idempotency without a live database."""

    def __init__(self, *, accept_persistence: bool = True) -> None:
        self.accept_persistence = accept_persistence
        self.runs: dict[str, HealthRun] = {}
        self.tickets: dict[str, Ticket] = {}
        self.intents: dict[str, AlertIntent] = {}

    @property
    def ticket_count(self) -> int:
        return len(self.tickets)

    @property
    def intent_count(self) -> int:
        return len(self.intents)

    @property
    def sent_count(self) -> int:
        return sum(item.status == "sent" for item in self.intents.values())

    def start_run(self, now: datetime) -> HealthRun:
        run = HealthRun(str(uuid.uuid4()), now, now)
        self.runs[run.run_id] = run
        return run

    def heartbeat(self, run_id: str, now: datetime) -> HealthRun:
        run = replace(self.runs[run_id], heartbeat_at=now)
        self.runs[run_id] = run
        return run

    def complete(self, run_id: str, now: datetime, **changes: object) -> HealthRun:
        code = changes.get("error_code")
        if code is not None and code not in ERROR_CODES:
            raise ValueError("error code is not allow-listed")
        run = replace(self.runs[run_id], completed_at=now, **changes)
        self.runs[run_id] = run
        return run

    def persist(self, item: SourceItem) -> bool:
        if not self.accept_persistence:
            return False
        key = stable_source_key(item.provider_id)
        self.tickets.setdefault(key, Ticket(key, item.received_at, item.priority))
        return True

    def create_alert_intent(
        self, dedup_key: str, state: str, source_run_id: str, now: datetime,
    ) -> AlertIntent:
        if len(dedup_key) != 64 or any(ch not in "0123456789abcdef" for ch in dedup_key):
            raise ValueError("dedup key must be 64 lowercase hexadecimal characters")
        existing = self.intents.get(dedup_key)
        if existing:
            updated = replace(existing, last_seen_at=now, source_run_id=source_run_id)
            self.intents[dedup_key] = updated
            return updated
        intent = AlertIntent(str(uuid.uuid4()), dedup_key, state, source_run_id, now, now)
        self.intents[dedup_key] = intent
        return intent
