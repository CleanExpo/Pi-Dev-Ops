"""margot.casual model resolution — the free ladder (RA-7434).

Founder ruling, 03/09/2026: the Telegram persona role ``margot.casual`` runs on
free models only. The ledger showed four different models answering it in 45
days; ``~moonshotai/kimi-latest`` alone cost $2.55 while the free path already
worked. Everything that decides which model answers that role lives here.

Extracted from ``provider_router.py`` on 07/09/2026. That file had grown to 909
lines against a 735-line baseline and the size gate refused it, correctly: its
own rule is "extract when you touch these; do not add to them". This block was
the whole of the addition and it is a self-contained concern, so it moves out
rather than the baseline moving up.

**Why the provider_router imports are lazy.** Three runtime symbols still live
there — ``ProviderModel``, ``_parse_provider_spec`` and
``_record_cost_safe``. Importing them at module scope would create a cycle,
because ``provider_router`` imports this module. ``_pr()`` defers the lookup to
call time, by which point ``provider_router`` is fully initialised: it is the
only caller of anything here.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only — never imported at runtime
    from .provider_router import Provider, ProviderModel

log = logging.getLogger("pi-ceo.provider_router")


def _pr():
    """`provider_router`, resolved at call time to avoid an import cycle."""
    from . import provider_router  # noqa: PLC0415

    return provider_router


class RefusedModelError(RuntimeError):
    """A model resolved for margot.casual is on the RA-7434 refusal list."""


MARGOT_CASUAL_ROLE = "margot.casual"
MARGOT_CASUAL_ENV = "TAO_MODEL_MARGOT_CASUAL"
# Founder ruling 21/10/2026: the local-model step and the previous step-2 model
# family are removed. Two OpenRouter ":free" models, then an error. There is no
# third step and no paid fallback.
MARGOT_CASUAL_LADDER: tuple[tuple[Provider, str], ...] = (
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("openrouter", "minimax/minimax-m3.1-flash:free"),
)
FREE_SUFFIX = ":free"
MARGOT_CASUAL_REFUSED_MARKERS = ("kimi", "moonshot", "anthropic", "claude", "sonnet")


# ── margot.casual resolution (RA-7434) ──────────────────────────────────────


def _margot_casual_refusal(provider: str, model_id: str) -> str | None:
    """Why margot.casual may not run `provider:model_id`, or None when it may.

    An ALLOWLIST of exactly the ladder entries, each of which must end ":free".
    A denylist was the first shape and it was wrong: `openrouter:openai/gpt-4o`
    matched none of the refused markers. Before 21/10/2026 the allowlist also
    admitted any local model and any OpenRouter ":free" id; both are gone, so
    an override can only re-select a ladder step.

    The marker list still runs FIRST, so an Anthropic model is refused by name
    even if someone puts it on the ladder.
    """
    probe = f"{provider}:{model_id}".lower()
    for marker in MARGOT_CASUAL_REFUSED_MARKERS:
        if marker in probe:
            return f"matches refused marker {marker!r}"
    if (provider, model_id) in MARGOT_CASUAL_LADDER and model_id.endswith(FREE_SUFFIX):
        return None
    return "is not a ':free' entry on the margot.casual ladder"


def _margot_casual_candidates() -> list[tuple[Provider, str, str]]:
    """Ordered (provider, model_id, source) margot.casual may use right now.

    An override is a single candidate. Nothing here consults TAO_CHEAP_*.
    """
    raw = (os.environ.get(MARGOT_CASUAL_ENV) or "").strip()
    if raw:
        parsed = _pr()._parse_provider_spec(raw)
        if parsed is not None:
            return [(parsed[0], parsed[1], f"env:{MARGOT_CASUAL_ENV}")]
        log.warning("provider_router: %s=%r is not provider:model — using the free ladder",
                    MARGOT_CASUAL_ENV, raw)
    return [(prov, model, f"ladder-step-{n}")
            for n, (prov, model) in enumerate(MARGOT_CASUAL_LADDER, start=1)]


def _refuse_if_forbidden(provider: str, model_id: str, source: str) -> None:
    reason = _margot_casual_refusal(provider, model_id)
    if reason is None:
        return
    raise RefusedModelError(
        f"{MARGOT_CASUAL_ROLE} may not run on {provider}:{model_id} (source {source}): "
        f"it {reason}. Founder ruling RA-7434: this role runs on free models only — "
        f"unset {MARGOT_CASUAL_ENV} or point it at a model on the ladder."
    )


def _resolve_margot_casual() -> ProviderModel:
    prov, model, source = _margot_casual_candidates()[0]
    _refuse_if_forbidden(prov, model, source)
    return _pr().ProviderModel(provider=prov, model_id=model, tier="cheap",
                         role=MARGOT_CASUAL_ROLE, source=source)


async def _call_ladder_step(prov: str, model: str, prompt: str, *, timeout_s: int,
                            session_id: str) -> tuple[int, str, float, str | None]:
    """Authorize the actual transport before each ladder step.

    OpenRouter is the only provider the ladder can dispatch. Anything else comes
    back as an error, never routed to OpenRouter under a model id it never serves.
    """
    import sys as _sys  # noqa: PLC0415
    from .provider_policy import require_transport

    if prov != "openrouter":
        return 1, "", 0.0, f"margot_casual_unsupported_provider: {prov}"
    try:
        require_transport(prov, role=MARGOT_CASUAL_ROLE, model_id=model)
        provider_mod = _sys.modules.get("app.server.provider_openrouter")
        if provider_mod is None:
            from . import provider_openrouter as provider_mod  # noqa: PLC0415
        return await provider_mod.call(
            prompt=prompt, model_id=model, timeout_s=timeout_s,
            role=MARGOT_CASUAL_ROLE, session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"{prov}_call_raised: {exc}"


async def _run_margot_casual(prompt: str, *, timeout_s: int, session_id: str,
                             ) -> tuple[int, str, float, str | None]:
    """Walk the free ladder at call time.

    A refusal comes back as an error TUPLE, never a raise. RA-7490 also
    fail-closes ``margot_bot._call_llm`` on any router raise, so a thrown
    refusal cannot reach a paid SDK. The tuple is still the contract:
    rc=1 makes the bot answer "unavailable" instead of treating the
    denial as something to recover from.
    """
    try:
        candidates = _margot_casual_candidates()
        for prov, model, source in candidates:
            _refuse_if_forbidden(prov, model, source)
    except RefusedModelError as exc:
        log.error("provider_router: %s", exc)
        return 1, "", 0.0, f"margot_casual_refused: {exc}"

    last_error = "no candidates"
    for prov, model, source in candidates:
        rc, text, cost, err = await _call_ladder_step(
            prov, model, prompt, timeout_s=timeout_s, session_id=session_id)
        if int(rc) == 0:
            _pr()._record_cost_safe(provider=prov, role=MARGOT_CASUAL_ROLE,
                                    model=model, cost_usd=float(cost or 0.0))
            return int(rc), text, cost, err
        last_error = f"{prov}:{model} ({source}): {err}"
        log.warning("provider_router: margot.casual %s — trying the next ladder step", last_error)
    return 1, "", 0.0, f"margot_casual_ladder_exhausted: {last_error}"
