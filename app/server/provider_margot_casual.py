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
MARGOT_CASUAL_OLLAMA_ENV = "MARGOT_OLLAMA_BASE_URL"
MARGOT_CASUAL_LADDER: tuple[tuple[Provider, str], ...] = (
    ("ollama", "gemma4:latest"),
    ("openrouter", "google/gemma-4-26b-a4b-it:free"),
    ("openrouter", "z-ai/glm-4.7-flash"),
)
MARGOT_CASUAL_REFUSED_MARKERS = ("kimi", "moonshot", "anthropic", "claude", "sonnet")


# ── margot.casual resolution (RA-7434) ──────────────────────────────────────


def _margot_casual_refusal(provider: str, model_id: str) -> str | None:
    """Why margot.casual may not run `provider:model_id`, or None when it may.

    An ALLOWLIST, not a denylist. A denylist was the first shape and it was
    wrong: `openrouter:openai/gpt-4o` matches none of the five refused markers,
    so a role the founder ruling puts on $0 models could be pointed straight at
    a paid one. A list of forbidden names can only ever be as complete as the
    person writing it; the set of models that cost nothing is the one that can
    be stated exactly. Three things are permitted and nothing else:

      * any (provider, model_id) on MARGOT_CASUAL_LADDER,
      * any ollama model — it runs locally, so it costs nothing,
      * any OpenRouter model whose id ends ":free".

    The marker list still runs FIRST, because an Anthropic model served free
    through OpenRouter is free and is still forbidden for this role by name.
    """
    probe = f"{provider}:{model_id}".lower()
    for marker in MARGOT_CASUAL_REFUSED_MARKERS:
        if marker in probe:
            return f"matches refused marker {marker!r}"
    if (provider, model_id) in MARGOT_CASUAL_LADDER:
        return None
    if provider == "ollama":
        return None
    if provider == "openrouter" and model_id.lower().endswith(":free"):
        return None
    return ("is not on the free ladder, is not an ollama model, and is not an "
            "OpenRouter ':free' model")


def _margot_ollama_base_url() -> str:
    """The Ollama margot.casual may use: MARGOT_OLLAMA_BASE_URL first, else the
    global OLLAMA_BASE_URL (only present off Railway — the start guard strips it),
    else "" meaning step 1 is not configured."""
    return (
        os.environ.get(MARGOT_CASUAL_OLLAMA_ENV) or os.environ.get("OLLAMA_BASE_URL") or ""
    ).strip()


def _ollama_configured_and_reachable() -> bool:
    """Ladder step 1 needs an explicit base URL — the localhost default
    provider_ollama falls back to is never a real Ollama on Railway."""
    base_url = _margot_ollama_base_url()
    if not base_url:
        return False
    try:
        import sys as _sys  # noqa: PLC0415
        ollama_mod = _sys.modules.get("app.server.provider_ollama")
        if ollama_mod is None:
            from . import provider_ollama as ollama_mod  # noqa: PLC0415
        return bool(ollama_mod.is_reachable(base_url=base_url))
    except Exception as exc:  # noqa: BLE001
        log.debug("provider_router: margot.casual ollama probe failed (%s)", exc)
        return False


def _margot_casual_candidates() -> list[tuple[Provider, str, str]]:
    """Ordered (provider, model_id, source) margot.casual may use right now.

    An override is a single candidate; the ladder skips step 1 when Ollama is
    not configured+reachable. Nothing here consults TAO_CHEAP_*.
    """
    raw = (os.environ.get(MARGOT_CASUAL_ENV) or "").strip()
    if raw:
        parsed = _pr()._parse_provider_spec(raw)
        if parsed is not None:
            return [(parsed[0], parsed[1], f"env:{MARGOT_CASUAL_ENV}")]
        log.warning("provider_router: %s=%r is not provider:model — using the free ladder",
                    MARGOT_CASUAL_ENV, raw)
    steps = list(enumerate(MARGOT_CASUAL_LADDER, start=1))
    if not _ollama_configured_and_reachable():
        steps = [(n, s) for n, s in steps if s[0] != "ollama"]
    return [(prov, model, f"ladder-step-{n}") for n, (prov, model) in steps]


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
    """One ladder step. Any raise becomes an error tuple so the walk continues.

    Looked up through sys.modules first so a test's monkeypatch.setitem wins
    over the cached import binding, which is how the rest of this router does
    it. Split out of _run_margot_casual to keep that under the 40-line limit.
    """
    import sys as _sys  # noqa: PLC0415

    # Explicit, not "ollama else openrouter". The old shape sent EVERY other
    # provider to provider_openrouter, so a claude_print or anthropic override
    # that slipped the refusal list would have been issued to OpenRouter under a
    # model id it never serves. _margot_casual_refusal refuses those first; this
    # refuses them again at the point of dispatch.
    if prov == "ollama":
        mod_name = "app.server.provider_ollama"
    elif prov == "openrouter":
        mod_name = "app.server.provider_openrouter"
    else:
        return 1, "", 0.0, f"margot_casual_unsupported_provider: {prov}"
    try:
        provider_mod = _sys.modules.get(mod_name)
        if provider_mod is None:
            if prov == "ollama":
                from . import provider_ollama as provider_mod  # noqa: PLC0415
            else:
                from . import provider_openrouter as provider_mod  # noqa: PLC0415
        extra = {"base_url": _margot_ollama_base_url()} if prov == "ollama" else {}
        return await provider_mod.call(
            prompt=prompt, model_id=model, timeout_s=timeout_s,
            role=MARGOT_CASUAL_ROLE, session_id=session_id, **extra,
        )
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"{prov}_call_raised: {exc}"


async def _run_margot_casual(prompt: str, *, timeout_s: int, session_id: str,
                             ) -> tuple[int, str, float, str | None]:
    """Walk the free ladder at call time.

    A refusal comes back as an error TUPLE, never a raise: margot_bot._call_llm
    wraps run_via_provider in `except Exception` and falls back to a direct
    Anthropic call — a raised refusal would land the role on the very model the
    ruling forbids. rc=1 makes the bot answer "unavailable" instead.
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
