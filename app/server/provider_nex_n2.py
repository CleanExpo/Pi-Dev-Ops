"""provider_nex_n2.py — nex-agi/nex-n2-pro:free secondary research/suggestion model."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("app.server.provider_nex_n2")

# ── Trial expiry marker ──────────────────────────────────────────────────────
# REMOVE AFTER: 2026-06-25 — re-evaluate or delete this module.
NEX_N2_FREE_UNTIL = "2026-06-25"

# ── Model registration ───────────────────────────────────────────────────────
NEX_N2_MODEL_ID = "nex-agi/nex-n2-pro:free"

# Roles where nex-n2-pro is allowed as a secondary model.
# model_policy.py does not police OpenRouter models by role (only Anthropic
# opus/sonnet/haiku short-names go through that gate).  We declare this here
# as documentation and for policy_allowed() callers.
NEX_N2_ALLOWED_ROLES: frozenset[str] = frozenset({
    "research",
    "research.realtime",
    "suggestion",
    "margot.synthesis",
    "margot.truth_check",
    "board",           # secondary opinion pass alongside primary
    "senior_brief",    # secondary research enrichment
})


def is_enabled() -> bool:
    """Return True when NEX_N2_RESEARCH_ENABLED is not explicitly disabled."""
    raw = os.environ.get("NEX_N2_RESEARCH_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def policy_allowed(role: str) -> bool:
    """Return True if role is allowed to call nex-n2-pro as secondary."""
    return role in NEX_N2_ALLOWED_ROLES


# ── Request builders ─────────────────────────────────────────────────────────


def _build_body(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """Build an OpenRouter chat-completions body for nex-n2-pro with reasoning.

    Sends the `reasoning` parameter so the model performs step-by-step
    thinking before answering.  The response will contain a `reasoning`
    field on the assistant message object with reasoning_details.

    Messages must be in OpenAI chat format:
        [{"role": "user"|"assistant"|"system", "content": "..."},
         # For assistant turns that had reasoning, include reasoning_details:
         {"role": "assistant", "content": "...",
          "reasoning": [{"type": "thinking", "thinking": "..."}]},
         ...]
    """
    return {
        "model": NEX_N2_MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.6,
        # Enable step-by-step reasoning.
        # Per OpenRouter docs: send {"effort": "high"} for maximum reasoning.
        "reasoning": {"effort": "high"},
    }


def _extract_text(response: dict[str, Any]) -> str:
    """Extract the assistant's text content from the chat-completions response."""
    choices = response.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return msg.get("content") or ""


def _extract_reasoning_details(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract reasoning_details from the assistant message.

    OpenRouter returns reasoning as a list under choices[0].message.reasoning.
    Each element is {"type": "thinking", "thinking": "<step text>"}.

    Returns an empty list when reasoning is absent (e.g. flag off, model
    doesn't support it, or the response was truncated).
    """
    choices = response.get("choices") or []
    if not choices:
        return []
    msg = choices[0].get("message") or {}
    details = msg.get("reasoning")
    if isinstance(details, list):
        return details
    return []


def _extract_cost_usd(response: dict[str, Any]) -> float:
    usage = response.get("usage") or {}
    cost = usage.get("cost") or usage.get("total_cost") or 0.0
    try:
        return float(cost)
    except (TypeError, ValueError):
        return 0.0


def build_assistant_message_with_reasoning(
    content: str,
    reasoning_details: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construct an assistant message dict that preserves reasoning_details.

    Use this when building multi-turn history so the model receives its own
    prior reasoning on the next turn (OpenRouter requirement for reasoning
    continuity).

    Returns:
        {"role": "assistant", "content": "...", "reasoning": [...]}
        or just {"role": "assistant", "content": "..."} when there are no
        reasoning_details to preserve.
    """
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning_details:
        msg["reasoning"] = reasoning_details
    return msg


# ── HTTP call ────────────────────────────────────────────────────────────────


async def call(
    *,
    prompt: str,
    role: str = "research",
    timeout_s: float = 120.0,
    max_tokens: int = 8192,
    session_id: str = "",
    history: list[dict[str, Any]] | None = None,
) -> tuple[int, str, float, str | None, list[dict[str, Any]]]:
    """Call nex-n2-pro:free on OpenRouter."""
    from app.server import provider_policy
    try:
        provider_policy.require_transport("openrouter")
    except provider_policy.ProviderPolicyError as exc:
        return 1, "", 0.0, str(exc), []
    if not is_enabled():
        log.debug("provider_nex_n2: disabled via NEX_N2_RESEARCH_ENABLED")
        return 1, "", 0.0, "nex_n2_disabled", []

    # Import provider_openrouter helpers to reuse header building
    try:
        from . import provider_openrouter as _por  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"nex_n2_import_failed: {exc}", []

    headers = _por._build_headers()
    if not headers:
        return 1, "", 0.0, "openrouter_no_api_key", []

    # Build message list: optional history + new user turn
    messages: list[dict[str, Any]] = list(history or [])
    messages.append({"role": "user", "content": prompt})

    body = _build_body(messages, max_tokens=max_tokens)

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"openrouter_httpx_import_failed: {exc}", []

    def _do_call() -> tuple[int, str, float, str | None, list[dict[str, Any]]]:
        url = "https://openrouter.ai/api/v1/chat/completions"
        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(url, headers=headers, json=body)
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"openrouter_call_raised: {exc}", []

        if r.status_code == 429:
            # Free-tier rate limit — caller should fall back to existing model
            log.warning(
                "provider_nex_n2: 429 rate-limited (free trial limit); "
                "caller should fall back. session=%s", session_id,
            )
            return 1, "", 0.0, "openrouter_http_429", []

        if r.status_code >= 400:
            snippet = (r.text or "")[:500]
            return 1, "", 0.0, (
                f"openrouter_http_{r.status_code}: {snippet}"
            ), []

        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"openrouter_bad_json: {exc}", []

        text = _extract_text(data)
        reasoning_details = _extract_reasoning_details(data)
        cost = _extract_cost_usd(data)

        if not text:
            return 1, "", cost, "openrouter_empty_response", reasoning_details

        log.info(
            "provider_nex_n2: %s: %d chars, reasoning_steps=%d, $%.6f (session=%s)",
            role, len(text), len(reasoning_details), cost, session_id or "?",
        )
        return 0, text, cost, None, reasoning_details

    return await asyncio.to_thread(_do_call)


# ── Secondary research pass ───────────────────────────────────────────────────


async def research_pass(
    prompt: str,
    *,
    role: str = "research",
    timeout_s: float = 120.0,
    max_tokens: int = 8192,
    session_id: str = "",
    history: list[dict[str, Any]] | None = None,
    fallback_text: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """Run a secondary research/suggestion pass with graceful fallback.

    Returns (text, reasoning_details).  On any failure (disabled, rate-limit,
    network error, etc.) returns (fallback_text, []) so the caller's primary
    path continues unaffected.

    This is the recommended entry point for callers — they do not need to
    inspect the rc/error tuple.
    """
    if not is_enabled():
        return fallback_text, []

    if not policy_allowed(role):
        log.debug(
            "provider_nex_n2: role=%s not in NEX_N2_ALLOWED_ROLES — skipping",
            role,
        )
        return fallback_text, []

    rc, text, _cost, error, reasoning_details = await call(
        prompt=prompt,
        role=role,
        timeout_s=timeout_s,
        max_tokens=max_tokens,
        session_id=session_id,
        history=history,
    )

    if rc != 0:
        log.warning(
            "provider_nex_n2: research_pass failed (role=%s error=%s) — "
            "falling back to primary model result",
            role, error,
        )
        return fallback_text, []

    return text, reasoning_details


__all__ = [
    "NEX_N2_MODEL_ID",
    "NEX_N2_FREE_UNTIL",
    "NEX_N2_ALLOWED_ROLES",
    "is_enabled",
    "policy_allowed",
    "build_assistant_message_with_reasoning",
    "call",
    "research_pass",
    "_build_body",
    "_extract_text",
    "_extract_reasoning_details",
    "_extract_cost_usd",
]
