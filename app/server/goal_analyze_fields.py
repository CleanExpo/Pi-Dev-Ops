"""Flatten nested analyze JSON into string fields for review and Linear."""
from __future__ import annotations

import json
from typing import Any

_TEXT_KEYS = (
    "context",
    "user_story",
    "current_behaviour",
    "expected_behaviour",
    "technical_requirements",
    "edge_cases",
    "dependencies",
    "rationale",
    "summary",
    "user_flow",
    "technical_flow",
    "examples",
    "implementation_notes",
    "risks",
    "affected_surfaces",
)


def as_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(as_text(x) for x in value if as_text(x))
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {as_text(val)}" for key, val in value.items() if as_text(val)
        )
    return str(value or "").strip()


def format_testing(value: Any) -> str:
    if not isinstance(value, dict):
        return as_text(value)
    parts: list[str] = []
    for key in ("unit", "integration", "e2e", "accessibility", "manual"):
        body = as_text(value.get(key))
        if body:
            parts.append(f"{key}:\n{body}")
    return "\n\n".join(parts) or as_text(value)


def format_scope(value: Any) -> str:
    if not isinstance(value, dict):
        return as_text(value)
    included = as_text(value.get("included"))
    excluded = as_text(value.get("excluded"))
    bits: list[str] = []
    if included:
        bits.append(f"Included:\n{included}")
    if excluded:
        bits.append(f"Not included:\n{excluded}")
    return "\n\n".join(bits)


def format_review(value: Any) -> str:
    if not isinstance(value, dict):
        return as_text(value)
    order = (
        "clarity",
        "scope",
        "technical_confidence",
        "testability",
        "main_risk",
    )
    parts = [f"{key}: {as_text(value.get(key))}" for key in order if as_text(value.get(key))]
    extra = [
        f"{key}: {as_text(val)}"
        for key, val in value.items()
        if key not in order and as_text(val)
    ]
    return "\n".join(parts + extra)


def format_block(value: Any, *, details_key: str = "details") -> str:
    if not isinstance(value, dict):
        return as_text(value)
    required = value.get("required")
    details = as_text(value.get(details_key))
    bits: list[str] = []
    if required is True:
        bits.append("Required.")
    elif required is False:
        bits.append("Not required.")
    if details:
        bits.append(details)
    return "\n".join(bits)


def flatten_ticket(item: dict[str, Any]) -> dict[str, str]:
    """Turn one model ticket (nested or flat) into string fields."""
    out: dict[str, str] = {}
    for key in _TEXT_KEYS:
        out[key] = as_text(item.get(key))
    out["acceptance"] = as_text(item.get("acceptance") or item.get("acceptance_criteria"))
    out["testing"] = format_testing(item.get("testing"))
    out["scope"] = format_scope(item.get("scope"))
    out["review"] = format_review(item.get("review"))
    out["ui_ux"] = format_block(item.get("ui_ux"))
    out["data_state"] = format_block(item.get("data_state"))
    out["ticket_id"] = as_text(item.get("id") or item.get("ticket_id"))
    out["priority"] = as_text(item.get("priority"))
    return out


def analysis_overlay(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Top-level review fields. Accepts both the new schema and the old flat one."""
    src = payload or {}
    ga = src.get("goal_analysis") if isinstance(src.get("goal_analysis"), dict) else {}
    summary = as_text(ga.get("summary") or src.get("summary"))
    user_flow = src.get("user_flow") if isinstance(src.get("user_flow"), dict) else {}
    technical_flow = (
        src.get("technical_flow") if isinstance(src.get("technical_flow"), dict) else {}
    )
    order = src.get("implementation_order")
    review = src.get("final_review")
    return {
        "summary": summary,
        "split_reason": as_text(src.get("split_reason")),
        "goal_analysis": ga,
        "user_flow": user_flow,
        "technical_flow": technical_flow,
        "implementation_order": order if isinstance(order, list) else [],
        "final_review": review if isinstance(review, dict) else {},
    }


def payload_score(obj: dict[str, Any]) -> int:
    """Prefer a full analyze payload over a nested fragment or the empty schema."""
    tickets = obj.get("tickets")
    score = 0
    if isinstance(tickets, list):
        score += min(len(tickets), 6)
        for item in tickets:
            if not isinstance(item, dict):
                continue
            title = as_text(item.get("title")).lower()
            if "human-written imperative title" in title:
                continue
            expected = as_text(
                item.get("expected_behaviour") or item.get("goal") or item.get("summary")
            )
            acceptance = as_text(item.get("acceptance") or item.get("acceptance_criteria"))
            if expected and acceptance:
                score += 8
    ga = obj.get("goal_analysis")
    if isinstance(ga, dict) and as_text(ga.get("summary")):
        score += 4
    if as_text(obj.get("split_reason")):
        score += 1
    return score


def parse_analyze_payload(text: str) -> dict[str, Any] | None:
    """Pick the analyze JSON object, not a nested review/schema fragment."""
    decoder = json.JSONDecoder()
    best: dict[str, Any] | None = None
    best_score = 0
    start = 0
    while True:
        index = text.find("{", start)
        if index < 0:
            break
        try:
            obj, _end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            start = index + 1
            continue
        if isinstance(obj, dict):
            score = payload_score(obj)
            if score > best_score:
                best = obj
                best_score = score
        start = index + 1
    return best if best_score > 0 else None
