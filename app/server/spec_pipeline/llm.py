"""Thin LLM helpers for spec pipeline (OpenRouter + optional SDK)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.server import provider_openrouter

log = logging.getLogger("pi-ceo.spec_pipeline.llm")

_JSON_SLICE = re.compile(r"\{[\s\S]*\}")


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract first JSON object from model output."""
    text = text.strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    m = _JSON_SLICE.search(text)
    if not m:
        raise ValueError("no JSON object in model output")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj


async def complete(
    *,
    prompt: str,
    system: str = "",
    model_id: str = "anthropic/claude-sonnet-4-6",
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
