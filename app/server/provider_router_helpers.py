"""provider_router_helpers.py — two dispatch blocks split out of provider_router.

provider_router.py is 735 lines against this repo's 300-line convention, and
CLAUDE.md's rule for a file that size is "extract when you touch them; do not
add to them". RA-7434 had to touch ``select_provider_model`` and
``run_via_provider`` (a margot.casual early return in each), and both were
already over the 40-line function limit, so the two blocks they could shed
live here. Behaviour is unchanged — this is a move, not a rewrite.

``_pr()`` defers the provider_router import to call time: provider_router
imports this module, so a module-scope import would be a cycle.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider_router import ProviderModel

log = logging.getLogger("pi-ceo.provider_router")


def _pr():
    from . import provider_router  # noqa: PLC0415

    return provider_router


def _corrected_for_downgrade(role: str, model: str, env_key: str) -> ProviderModel | None:
    """The tier default when `env_key` would downgrade `role`, else None.

    Extracted from select_provider_model (RA-7434), which was 72 lines
    against a 40-line convention. Behaviour unchanged; the comment below
    is the original, moved with its code.
    """
    # A per-role override may not DOWNGRADE a quality-critical role onto
    # the cheap-tier model. The previous change made this visible; making
    # it visible did not stop it happening, and every planner,
    # orchestrator, board, generator and evaluator call in production was
    # still being answered by the cheap model.
    #
    # Correction, not refusal: the role falls back to its tier default
    # rather than erroring. Refusing would take production down over a
    # config that has been live for months — the same reason the earlier
    # change stopped at observability. Correcting keeps every call
    # served while ending the downgrade, which is the outcome actually
    # wanted. CLAUDE.md already records what a too-cheap planner
    # produces: 5%-confidence plans and prose refusals.
    #
    # Deliberately narrow: it fires ONLY when the override names the
    # configured cheap model for a top/mid role. Any other override —
    # a different Anthropic model, a specific OpenRouter model, a local
    # Ollama pin — is honoured untouched, because the operator asking
    # for a specific capable model is a legitimate decision and this is
    # not a general-purpose model policy.
    if _pr()._is_tier_downgrade(role, model):
        tier = _pr().ROLE_TIER.get(role, "mid")
        corrected_prov, corrected_model = _pr()._tier_default(tier)
        log.warning(
            "provider_router: ignoring %s — a %s-tier role may not run on the "
            "cheap model %s; using %s:%s instead",
            env_key, tier, model, corrected_prov, corrected_model,
        )
        return _pr().ProviderModel(
            provider=corrected_prov, model_id=corrected_model,
            tier=tier, role=role, source="tier_downgrade_corrected",
        )
    return None


async def _run_tier0(prompt: str, *, role: str, session_id: str, timeout_s: int,
                      confidential: bool) -> tuple[int, str, float, str | None]:
    """Run the resolved tier-0 chain. Split out of run_via_provider (RA-7434).

    That function was 124 lines against a 40-line convention, and this branch
    had to add a margot.casual dispatch at its top. Behaviour is unchanged.
    """
    try:
        import sys as _sys  # noqa: PLC0415
        tier0_runner = _sys.modules.get("app.server.tier0_runner")
        if tier0_runner is None:
            from . import tier0_runner  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"tier0_runner_import_failed: {exc}"
    r = await tier0_runner.run_tier0(
        prompt, confidential=confidential, role=role,
        session_id=session_id, timeout_s=timeout_s,
    )
    if r.ok and r.cost_usd > 0:
        _pr()._record_cost_safe(
            provider=r.provider or "tier0", role=role,
            model=r.model_id or "", cost_usd=r.cost_usd,
        )
    return (0 if r.ok else 1), r.text, r.cost_usd, r.error
