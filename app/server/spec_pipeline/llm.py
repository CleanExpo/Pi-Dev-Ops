"""Thin LLM helpers for spec pipeline (OpenRouter + optional SDK)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.server import provider_openrouter
from app.server.model_registry import OPENROUTER_SONNET

log = logging.getLogger("pi-ceo.spec_pipeline.llm")

_JSON_SLICE = re.compile(r"\{[\s\S]*\}")


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract first JSON object from model output."""
    obj = try_parse_json_object(text)
    if obj is None:
        raise ValueError("no JSON object in model output")
    return obj


def try_parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort JSON object parse; returns None instead of raising."""
    cleaned = text.strip()
    fence = _JSON_FENCE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    if cleaned.startswith("{"):
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
  # Prefer the last JSON object — models often append JSON after markdown memos.
    start = cleaned.rfind("{")
    while start >= 0:
        chunk = cleaned[start:]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            m = _JSON_SLICE.search(chunk)
            if m:
                try:
                    obj = json.loads(m.group(0))
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
        start = cleaned.rfind("{", 0, start)
    m = _JSON_SLICE.search(cleaned)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


async def complete(
    *,
    prompt: str,
    system: str = "",
    model_id: str = OPENROUTER_SONNET,
    max_tokens: int = 4096,
    role: str = "spec_pipeline",
) -> tuple[str, float]:
    """OpenRouter completion; returns (text, cost_usd)."""
    full = f"{system}\n\n{prompt}" if system else prompt
    rc, text, cost, err = await provider_openrouter.call(
        prompt=full,
        model_id=model_id,
        max_tokens=max_tokens,
        role=role,
    )
    if rc != 0 or not text:
        raise RuntimeError(err or "llm call failed")
    return text, cost
