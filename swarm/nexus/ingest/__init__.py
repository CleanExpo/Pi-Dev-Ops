"""Outcomes ingestion adapters — one module per provider.

Phase B / B4. Each adapter is pure-logic: given a JSON-decoded webhook
body, return a ParseResult. The FastAPI webhook handler (Phase A) is
responsible for HMAC verification + writing the resulting Outcome to
the store; the parser modules here never touch I/O.

Idempotency: each provider's parser derives a deterministic outcome.id
from `<provider>:<event_id>`, so re-delivery of the same event always
collides on the primary key (Postgres ON CONFLICT DO NOTHING — see B4
webhook handler).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from ..types import Outcome

ParseResultKind = Literal[
    "ok", "malformed", "duplicate", "unknown_event", "ignored",
]


@dataclass(frozen=True)
class ParseResult:
    result: ParseResultKind
    event_id: str | None = None
    outcome: Outcome | None = None
    reason: str | None = None


def make_outcome_id(provider: str, event_id: str) -> str:
    """Deterministic outcome.id from provider + event_id.

    Collisions on re-delivery → upstream Postgres UPSERT becomes a
    no-op. 12-char hex keeps the ID short while keeping >2^48 entropy.
    """
    digest = hashlib.sha256(f"{provider}:{event_id}".encode("utf-8")).hexdigest()
    return f"out-{provider}-{digest[:12]}"


def safe_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
