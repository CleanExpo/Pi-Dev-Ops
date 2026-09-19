"""Spec completions through the shared subscription policy and identity checks."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.server import provider_router

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


async def complete_with_evidence(
    *,
    prompt: str,
    system: str = "",
    model_id: str | None = None,
    max_tokens: int = 4096,
    role: str = "spec_pipeline",
    provider: str | None = None,
) -> provider_router.ProviderExecution:
    """Use configured roles; only observed identities can inform a build decision.

    CLI transports do not expose a hard output-token limit. ``max_tokens`` is
    retained as a prompt budget, not claimed as an enforced billing limit.
    """
    if provider is not None and provider not in {"claude_print", "codex", "ollama"}:
        raise RuntimeError("subscription_only: explicit spec provider is unsupported")
    if provider is not None or model_id is not None:
        selected = provider_router.select_provider_model(role)
        if provider is not None and selected.provider != provider:
            raise RuntimeError("spec pipeline provider mismatch: configured route differs")
        if model_id is not None and model_id.removeprefix("anthropic/") != selected.model_id:
            raise RuntimeError("spec pipeline model mismatch: configured route differs")
    full = f"{system}\n\n{prompt}" if system else prompt
    full += f"\n\nKeep the response within approximately {max_tokens} tokens."
    outcome = await provider_router.run_via_provider_with_evidence(prompt=full, role=role)
    if outcome.rc != 0 or not outcome.text.strip():
        raise RuntimeError(outcome.error or "llm call failed")
    evidence = outcome.provenance
    actual = evidence.get("actual_model")
    if (evidence.get("auth_verified") is not True or evidence.get("model_verified") is not True
            or not isinstance(actual, str) or not actual.strip()
            or not evidence.get("provider") or not evidence.get("source")):
        raise RuntimeError("spec pipeline model identity or authorization unverified")
    if model_id is not None and model_id.removeprefix("anthropic/") != actual:
        raise RuntimeError("spec pipeline model mismatch: requested identity was not served")
    return outcome


async def complete(
    *, prompt: str, system: str = "", model_id: str | None = None,
    max_tokens: int = 4096, role: str = "spec_pipeline",
) -> tuple[str, float | None]:
    """Compatible text/cost interface; unobserved subscription cost remains None."""
    outcome = await complete_with_evidence(
        prompt=prompt, system=system, model_id=model_id, max_tokens=max_tokens, role=role,
    )
    return outcome.text, outcome.cost_usd
