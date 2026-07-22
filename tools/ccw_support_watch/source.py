"""Typed, fixture-driven source boundary for the CCW support watcher."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

PROHIBITED_FIELDS = frozenset({
    "address", "from", "from_email", "to", "to_email", "subject", "snippet",
    "body", "token", "secret", "raw_error", "error_detail", "payload",
    "raw_metadata", "provider_response",
})
ALLOWED_ITEM_FIELDS = frozenset({"provider_id", "received_at", "priority", "outbound_at"})


@dataclass(frozen=True, repr=False)
class SourceItem:
    provider_id: str
    received_at: datetime
    priority: str = "normal"
    outbound_at: tuple[datetime, ...] = ()

    def __repr__(self) -> str:
        return f"SourceItem(received_at={self.received_at!r}, priority={self.priority!r})"


@dataclass(frozen=True)
class SourceResult:
    ok: bool
    authenticated: bool
    items: tuple[SourceItem, ...] = ()
    error_code: str | None = None


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _item(raw: object) -> SourceItem:
    if not isinstance(raw, Mapping):
        raise ValueError("source item must be an object")
    fields = set(raw)
    if fields & PROHIBITED_FIELDS or not fields <= ALLOWED_ITEM_FIELDS:
        raise ValueError("source item violates bounded field contract")
    provider_id = raw.get("provider_id")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise KeyError("provider_id")
    priority = raw.get("priority", "normal")
    if priority not in {"normal", "urgent", "escalated"}:
        raise ValueError("invalid priority")
    outbound_raw = raw.get("outbound_at", ())
    if not isinstance(outbound_raw, (list, tuple)):
        raise ValueError("outbound_at must be a list")
    return SourceItem(
        provider_id=provider_id,
        received_at=_timestamp(raw.get("received_at")),
        priority=priority,
        outbound_at=tuple(_timestamp(value) for value in outbound_raw),
    )


def parse_source_response(envelope: object) -> SourceResult:
    """Validate a provider envelope without retaining raw errors or payloads."""
    if not isinstance(envelope, Mapping):
        return SourceResult(False, False, error_code="MALFORMED_RESPONSE")
    authenticated = envelope.get("authenticated") is True
    if not authenticated:
        return SourceResult(False, False, error_code="AUTH_FAILED")
    if envelope.get("ok") is not True:
        return SourceResult(False, True, error_code="QUERY_FAILED")
    raw_items = envelope.get("items")
    if not isinstance(raw_items, list):
        return SourceResult(False, True, error_code="MALFORMED_RESPONSE")
    try:
        items = tuple(_item(raw) for raw in raw_items)
    except KeyError:
        return SourceResult(False, True, error_code="MISSING_SOURCE_ID")
    except (TypeError, ValueError):
        return SourceResult(False, True, error_code="MALFORMED_RESPONSE")
    return SourceResult(True, True, items=items)
