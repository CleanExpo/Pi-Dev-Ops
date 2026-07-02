"""tier0_runner.py — UNI-2212: runtime chain-walk executor for the Tier-0 lane.

``tier0_lane`` resolves an ordered fallback chain of (provider, model_id) lanes;
this module RUNS it — invoking each lane in turn and falling through to the next
on failure, so a gathering task completes on the first lane that answers. This
is the "runtime chain-walk-on-failure" the resolver's docstring deferred.

Privacy gate (inherited from the resolver): ``confidential=True`` yields a
local-only chain, so OpenRouter (free or paid — both may train on inputs) is
never invoked with confidential data.

Free-pool accounting: every attempt on a FREE OpenRouter slug is booked against
the shared RPD/RPM ledger — conservatively, since a failed free attempt still
consumed account-level quota — so ``free_capacity_available()`` spills the chain
once the account pool is hit. Paid-spill and local lanes are never booked.

No Max-plan consumption: the Tier-0 chain contains only OpenRouter + local
Ollama lanes, never ``anthropic`` / ``claude_print`` — so gathering work here
takes zero load off the Claude Max plans by construction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import tier0_lane

log = logging.getLogger("app.server.tier0_runner")

DEFAULT_TIER0_TIMEOUT_S = 60.0


@dataclass
class Tier0Attempt:
    """One lane invocation and its outcome."""
    provider: str
    model_id: str
    rc: int
    error: str | None = None


@dataclass
class Tier0Result:
    """Outcome of one full chain walk."""
    ok: bool
    text: str
    provider: str | None
    model_id: str | None
    cost_usd: float
    confidential: bool
    attempts: list[Tier0Attempt] = field(default_factory=list)
    error: str | None = None


def _free_rpd_count() -> int:
    """Free-slug requests booked against today's RPD bucket (test/observability)."""
    return tier0_lane.free_rpd_today()


async def run_tier0(
    prompt: str,
    *,
    confidential: bool = False,
    role: str = "gather",
    session_id: str = "",
    max_tokens: int = 4096,
    timeout_s: float = DEFAULT_TIER0_TIMEOUT_S,
) -> Tier0Result:
    """Run one gathering task down the resolved Tier-0 chain with failover.

    ``ok`` is True as soon as a lane answers (rc==0). Confidential work routes
    local-only (privacy gate). Never raises — provider errors are captured
    per-attempt so the caller can inspect the full walk.
    """
    from . import provider_openrouter, provider_ollama

    chain = tier0_lane.resolve_tier0_chain(confidential=confidential)
    free = tier0_lane.free_slugs()
    attempts: list[Tier0Attempt] = []

    for provider, model_id in chain:
        if provider == "openrouter":
            call = provider_openrouter.call
        elif provider == "ollama":
            call = provider_ollama.call
        else:
            attempts.append(Tier0Attempt(provider, model_id, 1,
                                         f"unknown_provider:{provider}"))
            continue

        rc, text, cost, error = await call(
            prompt=prompt, model_id=model_id, role=role,
            session_id=session_id, max_tokens=max_tokens, timeout_s=timeout_s,
        )
        # Book free-pool usage regardless of outcome — a free attempt consumed
        # account-level quota whether or not it answered.
        if provider == "openrouter" and model_id in free:
            tier0_lane.record_free_request()
        attempts.append(Tier0Attempt(provider, model_id, rc, error))

        if rc == 0:
            return Tier0Result(
                ok=True, text=text, provider=provider, model_id=model_id,
                cost_usd=cost, confidential=confidential, attempts=attempts,
            )
        log.info("tier0_runner: %s:%s failed (%s); trying next lane",
                 provider, model_id, error)

    return Tier0Result(
        ok=False, text="", provider=None, model_id=None, cost_usd=0.0,
        confidential=confidential, attempts=attempts,
        error="all_tier0_lanes_failed",
    )


__all__ = ["Tier0Attempt", "Tier0Result", "run_tier0"]
