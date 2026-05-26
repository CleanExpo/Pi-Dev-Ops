"""Stripe webhook → Outcome.

Handles:
  invoice.paid                       → metric='invoice_paid', value_numeric=amount/100
  customer.subscription.created      → metric='subscription_created', value_numeric=mrr_estimate

Workspace attribution comes from `metadata.workspace_slug` on the
Stripe object (we set that when wiring per-client billing).
"""
from __future__ import annotations

from typing import Any

from ..types import Outcome
from . import ParseResult, make_outcome_id, safe_float, safe_str

HANDLED_EVENTS = {"invoice.paid", "customer.subscription.created"}


def parse(body: dict[str, Any], *, captured_at: str) -> ParseResult:
    if not isinstance(body, dict):
        return ParseResult(result="malformed", reason="body is not an object")

    event_id = safe_str(body.get("id"))
    event_type = safe_str(body.get("type"))
    if not event_id:
        return ParseResult(result="malformed", reason="missing event id")
    if event_type not in HANDLED_EVENTS:
        return ParseResult(result="ignored", event_id=event_id,
                           reason=f"event type {event_type!r} not handled")

    data_object = (body.get("data") or {}).get("object") or {}
    metadata = data_object.get("metadata") or {}
    workspace_slug = safe_str(metadata.get("workspace_slug"))
    workspace_id = safe_str(metadata.get("workspace_id"))
    if not workspace_slug or not workspace_id:
        return ParseResult(
            result="malformed", event_id=event_id,
            reason="metadata.workspace_slug + workspace_id required",
        )

    if event_type == "invoice.paid":
        metric = "invoice_paid"
        amount_cents = safe_float(data_object.get("amount_paid"))
        value_numeric = (amount_cents / 100.0) if amount_cents is not None else None
    else:  # customer.subscription.created
        metric = "subscription_created"
        items = (data_object.get("items") or {}).get("data") or []
        # Estimate MRR from the first item's unit_amount + quantity.
        unit_amount = safe_float((items[0] or {}).get("price", {}).get("unit_amount")) if items else None
        quantity = safe_float((items[0] or {}).get("quantity")) if items else None
        value_numeric = None
        if unit_amount is not None and quantity is not None:
            value_numeric = (unit_amount / 100.0) * quantity

    outcome = Outcome(
        id=make_outcome_id("stripe", event_id),
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        source="stripe",
        metric=metric,
        captured_at=captured_at,
        value_numeric=value_numeric,
        raw_payload={"id": event_id, "type": event_type},
    )
    return ParseResult(result="ok", event_id=event_id, outcome=outcome)
