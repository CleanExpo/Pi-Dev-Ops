"""provider_router.py — RA-1868 Wave 5.2: multi-provider model routing.

Three-tier cost-aware router that picks the right (provider, model_id)
per role/task class. Anthropic is reserved for the highest-quality work
(top tier — planner, orchestrator, Board deliberation, multi-agent
debate). OpenRouter handles the cheap tier (Margot conversational
turns, intent classification, monitor cycles).

Tier mapping (defaults; all overridable via env):

  TIER 1 — TOP    Anthropic Opus 4.7
                  Roles: planner, orchestrator, board, debate.drafter,
                  debate.redteam, margot.synthesis (Phase 2)
                  Env: TAO_TOP_MODEL=claude-opus-4-7

  TIER 2 — MID    Anthropic Sonnet 4.6
                  Roles: generator, evaluator, senior-brief
                  Env: TAO_MID_MODEL=claude-sonnet-4-6

  TIER 3 — CHEAP  OpenRouter → Gemma 3 27B (default; configurable)
                  Roles: margot.casual, intent_classify, monitor,
                  guardian, scribe.draft
                  Env: TAO_CHEAP_MODEL=google/gemma-3-27b-it

Per-role override:

  Each role can override its tier model via env:
    TAO_MODEL_<ROLE_UPPERCASED>=<provider>:<model_id>

  Example:
    TAO_MODEL_MARGOT_CASUAL=openrouter:meta-llama/llama-3.3-70b-instruct
    TAO_MODEL_INTENT_CLASSIFY=openrouter:mistralai/mistral-small-3.1

  Provider prefix is required: ``anthropic:`` or ``openrouter:``.

The router does NOT enforce model_policy.OPUS_ALLOWED_ROLES — that gate
still fires inside session_sdk._run_claude_via_sdk for Anthropic calls.
The router just picks; the existing policy still polices.

Public API:
  select_provider_model(role, task_class="default") -> ProviderModel
  is_anthropic(provider_model) -> bool
  is_openrouter(provider_model) -> bool

  run_via_provider(prompt, *, role, task_class, ...)
      -> tuple[rc, text, cost_usd, error]
      Async unified entry that dispatches to the right SDK.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger("app.server.provider_router")

Provider = Literal["anthropic", "openrouter", "ollama"]


# ── Defaults — all env-overridable ──────────────────────────────────────────

DEFAULT_TOP_MODEL = "claude-opus-4-7"
DEFAULT_MID_MODEL = "claude-sonnet-4-6"

# Cheap tier resolution:
#   1. Probe Ollama at localhost:11434 (or OLLAMA_BASE_URL).
#   2. If reachable → ollama:DEFAULT_CHEAP_LOCAL_MODEL (free, private, fast).
#   3. If not reachable → openrouter:DEFAULT_CHEAP_REMOTE_MODEL (paid fallback).
#
# Founder can:
#   - Override the local model via TAO_CHEAP_LOCAL_MODEL=<ollama-model-tag>
#   - Override the remote model via TAO_CHEAP_REMOTE_MODEL=<openrouter-id>
#   - Force one or the other via TAO_CHEAP_PROVIDER=ollama|openrouter (skips probe)
#   - Override per-role via TAO_MODEL_<ROLE> (highest precedence)
DEFAULT_CHEAP_LOCAL_MODEL = "gemma4:latest"

# OpenRouter remote-fallback default: Gemma 4 26B A4B (instruction-tuned).
# OpenRouter offers four Gemma 4 variants — pick by use case:
#   google/gemma-4-26b-a4b-it       — paid, ~$0.06/M in, $0.33/M out (default)
#   google/gemma-4-26b-a4b-it:free  — free tier, rate-limited
#   google/gemma-4-31b-it           — paid, ~$0.13/M in, $0.38/M out
#   google/gemma-4-31b-it:free      — free tier, rate-limited
# Override via TAO_CHEAP_REMOTE_MODEL env at deploy time.
DEFAULT_CHEAP_REMOTE_MODEL = "google/gemma-4-26b-a4b-it"

# Role → tier mapping (top/mid/cheap). Roles not listed default to "mid".
ROLE_TIER: dict[str, str] = {
    # Top tier — quality-critical reasoning
    "planner":           "top",
    "orchestrator":      "top",
    "board":             "top",
    "debate.drafter":    "top",
    "debate.redteam":    "top",
    "margot.synthesis":  "top",  # Phase-2 research integration
    "margot.truth_check": "top",  # RA-1886: Grok contrarian/truth-seeker voice
    "realtime_lookup":   "top",  # RA-1903: Perplexity Sonar real-time web data
    "research.realtime": "top",  # RA-1903: Sonar deep research live multi-step
    "portfolio.synthesis": "top",  # RA-1892: cross-portfolio daily pulse synthesis
    # Mid tier — production-quality output
    "generator":         "mid",
    "evaluator":         "mid",
    "senior_brief":      "mid",
    # Cheap tier — high-throughput, lower stakes
    "margot.casual":     "cheap",
    "intent_classify":   "cheap",
    "monitor":           "cheap",
    "guardian":          "cheap",
    "scribe.draft":      "cheap",
}


@dataclass
class ProviderModel:
    """One concrete (provider, model_id, tier) selection."""
    provider: Provider
    model_id: str
    tier: str  # "top" | "mid" | "cheap"
    role: str
    source: str  # "default" | "env_role_override" | "env_tier_default"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _env_role_key(role: str) -> str:
    """Convert role string to env var key."""
    return "TAO_MODEL_" + re.sub(r"[^A-Za-z0-9]+", "_", role).strip("_").upper()


def _parse_provider_spec(spec: str) -> tuple[Provider, str] | None:
    """Parse '<provider>:<model_id>' env value. Returns None on malformed.

    OpenRouter model_ids contain colons (e.g. "openrouter:google/gemma-3"),
    so we split on the first colon only.
    """
    spec = (spec or "").strip()
    if ":" not in spec:
        return None
    prov, model = spec.split(":", 1)
    prov = prov.strip().lower()
    model = model.strip()
    if prov not in ("anthropic", "openrouter", "ollama"):
        log.warning("provider_router: unknown provider %r in spec %r — skipping",
                    prov, spec)
        return None
    if not model:
        return None
    return prov, model  # type: ignore[return-value]


def _tier_default(tier: str) -> tuple[Provider, str]:
    """Resolve tier → (provider, model_id) using env overrides.

    Cheap tier resolution order:
      1. Legacy TAO_CHEAP_MODEL env (honoured for backwards compat;
         routed via Anthropic if claude-*, OpenRouter if "/" in id,
         Ollama otherwise).
      2. TAO_CHEAP_PROVIDER=ollama|openrouter explicit pin.
      3. Ollama reachability probe → if reachable, use local.
      4. Otherwise → OpenRouter remote.
    """
    if tier == "top":
        model = (os.environ.get("TAO_TOP_MODEL") or DEFAULT_TOP_MODEL).strip()
        return "anthropic", model
    if tier == "mid":
        model = (os.environ.get("TAO_MID_MODEL") or DEFAULT_MID_MODEL).strip()
        return "anthropic", model

    # Cheap tier — multi-step resolution
    return _resolve_cheap_tier()


def _resolve_cheap_tier() -> tuple[Provider, str]:
    """Pick (provider, model_id) for the cheap tier.

    Layers (most specific wins):
      1. TAO_CHEAP_MODEL — legacy single-knob (provider auto-detected
         from model_id shape).
      2. TAO_CHEAP_PROVIDER=ollama|openrouter explicit pin combined with
         TAO_CHEAP_LOCAL_MODEL / TAO_CHEAP_REMOTE_MODEL.
      3. Ollama reachability probe → local if up, OpenRouter if not.
    """
    # Layer 1: legacy single-knob
    legacy = (os.environ.get("TAO_CHEAP_MODEL") or "").strip()
    if legacy:
        if legacy.startswith("claude-"):
            return "anthropic", legacy
        if "/" in legacy:
            # OpenRouter style (vendor/model)
            return "openrouter", legacy
        # Otherwise treat as a local Ollama tag
        return "ollama", legacy

    # Layer 2: explicit provider pin
    pinned = (os.environ.get("TAO_CHEAP_PROVIDER") or "").strip().lower()
    local_model = (
        os.environ.get("TAO_CHEAP_LOCAL_MODEL") or DEFAULT_CHEAP_LOCAL_MODEL
    ).strip()
    remote_model = (
        os.environ.get("TAO_CHEAP_REMOTE_MODEL") or DEFAULT_CHEAP_REMOTE_MODEL
    ).strip()

    if pinned == "ollama":
        return "ollama", local_model
    if pinned == "openrouter":
        return "openrouter", remote_model
    if pinned and pinned not in ("ollama", "openrouter"):
        log.warning(
            "provider_router: unknown TAO_CHEAP_PROVIDER=%r — falling through to probe",
            pinned,
        )

    # Layer 3: probe-based selection
    try:
        import sys as _sys  # noqa: PLC0415
        ollama_mod = _sys.modules.get("app.server.provider_ollama")
        if ollama_mod is None:
            from . import provider_ollama as ollama_mod  # noqa: PLC0415
        if ollama_mod.is_reachable():
            log.debug(
                "provider_router: cheap tier → ollama:%s (local reachable)",
                local_model,
            )
            return "ollama", local_model
    except Exception as exc:  # noqa: BLE001
        log.debug("provider_router: ollama probe failed (%s)", exc)

    log.debug(
        "provider_router: cheap tier → openrouter:%s (local unreachable)",
        remote_model,
    )
    return "openrouter", remote_model


# ── Public API ──────────────────────────────────────────────────────────────


def select_provider_model(role: str,
                            task_class: str = "default") -> ProviderModel:
    """Pick the (provider, model_id) for one role.

    Resolution order:
      1. Per-role env override: TAO_MODEL_<ROLE>=provider:model_id
      2. Tier mapping → tier env (TAO_TOP_MODEL / TAO_MID_MODEL / TAO_CHEAP_MODEL)
      3. Hardcoded defaults

    task_class is reserved for future per-task fan-out (e.g.
    margot.casual.classify could route differently from margot.casual.reply
    even within the same role). Today it's a no-op label that lands in
    audit + cost-tracking metadata.
    """
    # 1. Per-role env override
    env_key = _env_role_key(role)
    raw = os.environ.get(env_key) or ""
    if raw:
        parsed = _parse_provider_spec(raw)
        if parsed is not None:
            prov, model = parsed
            log.debug("provider_router: %s overridden via %s = %s:%s",
                      role, env_key, prov, model)
            return ProviderModel(
                provider=prov, model_id=model,
                tier=ROLE_TIER.get(role, "mid"),
                role=role, source="env_role_override",
            )

    # 2. Tier mapping → tier defaults
    tier = ROLE_TIER.get(role, "mid")
    prov, model = _tier_default(tier)
    return ProviderModel(
        provider=prov, model_id=model,
        tier=tier, role=role,
        source="env_tier_default",
    )


def is_anthropic(pm: ProviderModel) -> bool:
    return pm.provider == "anthropic"


def is_openrouter(pm: ProviderModel) -> bool:
    return pm.provider == "openrouter"


def is_ollama(pm: ProviderModel) -> bool:
    return pm.provider == "ollama"


# ── Unified async entry ─────────────────────────────────────────────────────


async def run_via_provider(prompt: str, *, role: str,
                             task_class: str = "default",
                             timeout_s: int = 120,
                             workspace: str | None = None,
                             session_id: str = "",
                             thinking: str = "adaptive",
                             ) -> tuple[int, str, float, str | None]:
    """Single dispatch entry. Returns (rc, text, cost_usd, error_or_None).

    Picks (provider, model_id) via select_provider_model, then routes to
    the right SDK. Anthropic still fires through session_sdk to preserve
    the model_policy gate; OpenRouter goes through provider_openrouter.
    """
    pm = select_provider_model(role, task_class=task_class)

    if pm.provider == "anthropic":
        try:
            # Look up via sys.modules first so test monkeypatches via
            # monkeypatch.setitem(sys.modules, "app.server.session_sdk", ...)
            # win over the cached import binding.
            import sys as _sys  # noqa: PLC0415
            session_sdk = _sys.modules.get("app.server.session_sdk")
            if session_sdk is None:
                from . import session_sdk  # noqa: PLC0415
            _run_claude_via_sdk = session_sdk._run_claude_via_sdk
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"anthropic_sdk_import_failed: {exc}"
        try:
            rc, text, cost = await _run_claude_via_sdk(
                prompt=prompt,
                model=pm.model_id,
                workspace=workspace or "",
                timeout=timeout_s,
                session_id=session_id,
                phase=role,
                thinking=thinking,
            )
            rc_i = int(rc)
            cost_f = float(cost or 0.0)
            if rc_i == 0 and cost_f > 0:
                _record_cost_safe(
                    provider="anthropic", role=role, model=pm.model_id,
                    cost_usd=cost_f,
                )
            return rc_i, text or "", cost_f, None
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"anthropic_sdk_call_raised: {exc}"

    # Ollama path (local; free)
    if pm.provider == "ollama":
        try:
            import sys as _sys  # noqa: PLC0415
            provider_ollama = _sys.modules.get("app.server.provider_ollama")
            if provider_ollama is None:
                from . import provider_ollama  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"ollama_import_failed: {exc}"
        result = await provider_ollama.call(
            prompt=prompt, model_id=pm.model_id,
            timeout_s=timeout_s, role=role, session_id=session_id,
        )
        # Ollama is free (cost_usd=0.0) but we still record for completeness
        if int(result[0]) == 0:
            _record_cost_safe(
                provider="ollama", role=role, model=pm.model_id,
                cost_usd=float(result[2] or 0.0),
            )
        return result

    # OpenRouter path (remote; paid)
    try:
        import sys as _sys  # noqa: PLC0415
        provider_openrouter = _sys.modules.get("app.server.provider_openrouter")
        if provider_openrouter is None:
            from . import provider_openrouter  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"openrouter_import_failed: {exc}"
    result = await provider_openrouter.call(
        prompt=prompt, model_id=pm.model_id,
        timeout_s=timeout_s, role=role, session_id=session_id,
    )
    if int(result[0]) == 0:
        _record_cost_safe(
            provider="openrouter", role=role, model=pm.model_id,
            cost_usd=float(result[2] or 0.0),
        )
    return result


def _record_cost_safe(
    *, provider: str, role: str, model: str, cost_usd: float,
    tokens_in: int = 0, tokens_out: int = 0,
) -> None:
    """Best-effort budget tracker hook — must never raise."""
    try:
        import sys as _sys  # noqa: PLC0415
        bt = _sys.modules.get("swarm.budget_tracker")
        if bt is None:
            from swarm import budget_tracker as bt  # noqa: PLC0415
        bt.record_cost(
            provider=provider, role=role, model=model,
            cost_usd=cost_usd, tokens_in=tokens_in, tokens_out=tokens_out,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("provider_router: budget_tracker hook failed: %s", exc)


__all__ = [
    "Provider", "ProviderModel", "ROLE_TIER",
    "DEFAULT_TOP_MODEL", "DEFAULT_MID_MODEL",
    "DEFAULT_CHEAP_LOCAL_MODEL", "DEFAULT_CHEAP_REMOTE_MODEL",
    "select_provider_model", "run_via_provider",
    "is_anthropic", "is_openrouter", "is_ollama",
]
