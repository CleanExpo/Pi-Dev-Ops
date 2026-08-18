"""provider_router.py — RA-1868 Wave 5.2: multi-provider model routing.

Three-tier cost-aware router that picks the right (provider, model_id)
per role/task class. Anthropic is reserved for the highest-quality work
(top tier — planner, orchestrator, Board deliberation, multi-agent
debate). OpenRouter handles the cheap tier (Margot conversational
turns, intent classification, monitor cycles).

Tier mapping (defaults; all overridable via env):

  TIER 1 — TOP    Anthropic Opus 5
                  Roles: planner, orchestrator, board, debate.drafter,
                  debate.redteam, margot.synthesis (Phase 2)
                  Env: TAO_TOP_MODEL=claude-opus-5

  TIER 2 — MID    Anthropic Sonnet 5
                  Roles: generator, evaluator, senior-brief
                  Env: TAO_MID_MODEL=claude-sonnet-5

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

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.server.model_registry import ANTHROPIC_OPUS, ANTHROPIC_SONNET

log = logging.getLogger("app.server.provider_router")

Provider = Literal["anthropic", "openrouter", "ollama", "claude_print"]


# ── Defaults — all env-overridable ──────────────────────────────────────────

# Founder directive 2026-08-19: OpenRouter is tried FIRST on every paid tier.
# The Anthropic key carries a $20 cap, so Anthropic is the FALLBACK and must
# never be the default path. "First" is only meaningful if there is a second:
# run_via_provider falls back to the models below when OpenRouter cannot serve
# (no key / no credit / rate limited). Without that fallback an absent
# OPENROUTER_API_KEY would take the whole top+mid surface down.
DEFAULT_TOP_PROVIDER: Provider = "openrouter"
DEFAULT_TOP_MODEL = "qwen/qwen3.8-27b"
DEFAULT_MID_PROVIDER: Provider = "openrouter"
DEFAULT_MID_MODEL = "qwen/qwen3.8-27b"

# Anthropic fallback — reached only when OpenRouter cannot serve the request.
FALLBACK_TOP_MODEL = ANTHROPIC_OPUS
FALLBACK_MID_MODEL = ANTHROPIC_SONNET

# OpenRouter failures that mean "this provider cannot serve you at all" and so
# justify spending the capped Anthropic key. A malformed request or a model
# error is NOT here: retrying those on Anthropic burns the cap without any
# prospect of a better answer.
FALLBACK_TRIGGER_ERRORS = (
    "openrouter_no_api_key",
    "openrouter_http_402",  # insufficient credit
    "openrouter_http_429",  # rate limited
)

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
    "sprinkle.lessons":  "cheap",  # RA-2995: analyse_lessons cluster-title naming (Gemma 4 first sprinkle migration)
    "sprinkle.triage":   "cheap",  # RA-2995: triage real/false-positive verdict on scanner findings
    "sprinkle.feedback": "cheap",  # RA-2995: feedback_loop neutral-outcome pattern naming
    "sprinkle.pulse":    "cheap",  # RA-2995: portfolio_pulse BOARD-TRIGGER structured extraction
    "sprinkle.board_prebrief": "cheap",  # RA-2995: 5-bullet pre-brief before daily board meeting (final sprinkle)
    # Secondary research roles — served by nex-n2-pro:free (trial until 2026-06-25)
    # The primary model for these roles is still determined by their tier above;
    # nex-n2-pro runs as a secondary pass via provider_nex_n2.research_pass().
    "research":            "mid",   # generic research pass
    "suggestion":          "cheap", # suggestion generation (secondary opinion)
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
    if prov not in ("anthropic", "openrouter", "ollama", "claude_print"):
        log.warning("provider_router: unknown provider %r in spec %r — skipping",
                    prov, spec)
        return None
    if not model:
        return None
    return prov, model  # type: ignore[return-value]


def _tier_default(tier: str) -> tuple[Provider, str]:
    """Resolve tier → (provider, model_id) using env overrides.

    Top/mid tier resolution order:
      1. TAO_{TOP,MID}_USE_CLAUDE_PRINT=1 → route through `claude --print`
         subprocess ($0 marginal under Claude Max plan, per
         `[[feedback-model-routing-max-first]]`).
      2. TAO_{TOP,MID}_MODEL env model_id (or default).
      3. Provider: anthropic.

    Cheap tier resolution order:
      1. Legacy TAO_CHEAP_MODEL env (honoured for backwards compat;
         routed via Anthropic if claude-*, OpenRouter if "/" in id,
         Ollama otherwise).
      2. TAO_CHEAP_PROVIDER=ollama|openrouter explicit pin.
      3. Ollama reachability probe → if reachable, use local.
      4. Otherwise → OpenRouter remote.
    """
    if tier in ("top", "mid"):
        return _resolve_paid_tier(tier)

    # Tier-0 gathering lane (UNI-2212) — free OpenRouter first, capacity-aware,
    # spilling to paid/local. Returns the head lane; callers needing failover
    # walk tier0_lane.resolve_tier0_chain() directly.
    if tier == "tier0":
        from . import tier0_lane  # noqa: PLC0415
        return tier0_lane.select_tier0_lane()  # type: ignore[return-value]

    # Cheap tier — multi-step resolution
    return _resolve_cheap_tier()


def _detect_provider(model_id: str) -> Provider:
    """Infer the provider from a bare model id.

    Same shape test the cheap tier applies to TAO_CHEAP_MODEL: ``claude-*`` is
    Anthropic, ``vendor/model`` is OpenRouter, anything else is a local Ollama
    tag. Deliberately duplicated rather than shared with _resolve_cheap_tier —
    that function is live production routing and this change has no business
    editing it.

    This is what makes ``TAO_TOP_MODEL=qwen/qwen3.8-27b`` reach OpenRouter.
    Before, the bare slug was handed to the Anthropic SDK as an unknown model.
    """
    if model_id.startswith("claude-"):
        return "anthropic"
    if "/" in model_id:
        return "openrouter"
    return "ollama"


def _resolve_paid_tier(tier: str) -> tuple[Provider, str]:
    """Resolve the top/mid tier to (provider, model_id).

    Layers, most specific first:
      1. TAO_{TOP,MID}_MODEL as an explicit ``provider:model_id`` spec.
      2. TAO_{TOP,MID}_MODEL as a bare model id, provider inferred from shape.
      3. TAO_{TOP,MID}_USE_CLAUDE_PRINT=1 — $0 marginal under the Max plan, so
         it outranks the paid default but not an explicit model pin.
      4. Default: OpenRouter qwen/qwen3.8-27b (founder directive 2026-08-19).
    """
    env_key = "TAO_TOP_MODEL" if tier == "top" else "TAO_MID_MODEL"
    print_key = (
        "TAO_TOP_USE_CLAUDE_PRINT" if tier == "top" else "TAO_MID_USE_CLAUDE_PRINT"
    )
    use_print = os.environ.get(print_key, "").strip() == "1"

    raw = (os.environ.get(env_key) or "").strip()
    if raw:
        parsed = _parse_provider_spec(raw)
        if parsed is not None:
            return parsed
        if use_print:
            return "claude_print", raw
        return _detect_provider(raw), raw

    model = DEFAULT_TOP_MODEL if tier == "top" else DEFAULT_MID_MODEL
    if use_print:
        # Model id kept as the audit label, matching prior behaviour.
        return "claude_print", model
    provider = DEFAULT_TOP_PROVIDER if tier == "top" else DEFAULT_MID_PROVIDER
    return provider, model


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


def _is_tier_downgrade(role: str, model_id: str) -> bool:
    """True when `model_id` is the configured cheap model for a top/mid role.

    Single predicate shared by the recorder and the correction. They were two
    copies of the same condition for exactly one commit, which is the shape of
    bug where a gate logs one thing and enforces another — the ledger says a
    downgrade happened while the router quietly allows it, or the reverse.
    """
    if ROLE_TIER.get(role) not in ("top", "mid"):
        return False
    cheap_model = (os.environ.get("TAO_CHEAP_REMOTE_MODEL") or "").strip()
    return bool(cheap_model) and model_id.strip() == cheap_model


def _record_tier_downgrade(role: str, provider: str, model_id: str, env_key: str) -> None:
    """Record when a per-role env override runs a quality-critical role on the cheap model.

    ROLE_TIER declares planner, orchestrator and board as "top — quality-critical
    reasoning", and generator/evaluator as "mid — production-quality output". A per-role
    override is resolution step 1 and the tier mapping is step 2, so an override silently
    replaces the tier decision and nothing anywhere notices.

    That is not hypothetical. Production currently routes every one of those roles to the
    model configured as the CHEAP tier, and the divergence was invisible for months:
    model_policy guards a different path (it reads config.yaml, and this module states at
    the top that it does not enforce OPUS_ALLOWED_ROLES), and that gate is a ceiling
    anyway — it only ever asks whether something is opus when it should not be. Nothing
    asked whether a model was good enough for the role. CLAUDE.md records that Haiku had
    to be retired from planning for 5%-confidence plans and prose refusals; that lesson
    lived as prose, not as a control.

    Fire-and-forget observability, deliberately NOT a gate. Blocking here would take
    production down on a config that has been live for months; the defect was that the
    downgrade was unobservable, so the fix is to make it observable.
    """
    if not _is_tier_downgrade(role, model_id):
        return
    tier = ROLE_TIER.get(role)
    try:
        from . import model_policy as _mp
        path = _mp.VIOLATIONS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "role": role,
                "requested": f"{tier}-tier model",
                "granted": f"{provider}:{model_id}",
                "reason": (f"{env_key} routes a {tier}-tier role to the cheap-tier model; "
                           "the ROLE_TIER mapping was bypassed by a per-role override"),
                "caller": "provider_router.select_provider_model",
            }) + "\n")
        log.warning("provider_router: %s-tier role %r routed to cheap model %s:%s via %s",
                    tier, role, provider, model_id, env_key)
    except Exception as exc:  # never break a build over a log line
        log.error("provider_router: failed to record tier downgrade (non-fatal): %s", exc)


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
            _record_tier_downgrade(role, prov, model, env_key)

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
            if _is_tier_downgrade(role, model):
                tier = ROLE_TIER.get(role, "mid")
                corrected_prov, corrected_model = _tier_default(tier)
                log.warning(
                    "provider_router: ignoring %s — a %s-tier role may not run on the "
                    "cheap model %s; using %s:%s instead",
                    env_key, tier, model, corrected_prov, corrected_model,
                )
                return ProviderModel(
                    provider=corrected_prov, model_id=corrected_model,
                    tier=tier, role=role, source="tier_downgrade_corrected",
                )

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


def is_claude_print(pm: ProviderModel) -> bool:
    return pm.provider == "claude_print"


# ── claude --print subprocess wrapper ───────────────────────────────────────

CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "claude")


async def _run_via_claude_print(
    prompt: str, *, timeout_s: int = 120,
) -> tuple[int, str, float, str | None]:
    """Dispatch one prompt to `claude --print`. Returns (rc, text, cost_usd, error).

    Always reports cost_usd=0.0 — `claude --print` runs under the active Claude
    Code Max session, which has no per-call billing. Subprocess overhead is
    ~3-5s for cold start; acceptable for the cron-launched workers that this
    router fronts.

    The model arg is intentionally NOT passed — `claude --print` uses whatever
    model is configured in the user's Claude Code config (set via `/model` or
    settings.json). The model_id surfaces via the ProviderModel for audit /
    observability only.
    """
    def _blocking_run() -> tuple[int, str, str]:
        import subprocess as _sp  # noqa: PLC0415
        try:
            r = _sp.run(
                [CLAUDE_CLI, "--print", prompt],
                capture_output=True, text=True, timeout=timeout_s, check=False,
            )
            return r.returncode, r.stdout, r.stderr
        except FileNotFoundError:
            return 127, "", f"claude CLI not found at {CLAUDE_CLI}"
        except _sp.TimeoutExpired:
            return 124, "", f"claude --print timed out after {timeout_s}s"

    rc, stdout, stderr = await asyncio.to_thread(_blocking_run)
    if rc != 0:
        return rc, "", 0.0, stderr.strip() or f"claude --print exit {rc}"
    return 0, stdout.strip(), 0.0, None


# ── Unified async entry ─────────────────────────────────────────────────────


def _anthropic_fallback_model(tier: str) -> str | None:
    """Which Anthropic model backs up a failed OpenRouter call, if any.

    Only the paid tiers fall back. The cheap tier already has its own
    ollama/openrouter resolution and must never spend the capped Anthropic key.
    ``TAO_ANTHROPIC_FALLBACK=0`` disables the fallback outright, for when the
    $20 cap matters more than availability.
    """
    if os.environ.get("TAO_ANTHROPIC_FALLBACK", "").strip() == "0":
        return None
    if tier == "top":
        return FALLBACK_TOP_MODEL
    if tier == "mid":
        return FALLBACK_MID_MODEL
    return None


def _openrouter_cannot_serve(error: str | None) -> bool:
    """True when the OpenRouter error means the provider is unusable.

    Narrow on purpose: a 400 or a model-specific error would fail on Anthropic
    too, so retrying it just spends the capped key for nothing.
    """
    if not error:
        return False
    return any(error.startswith(e) for e in FALLBACK_TRIGGER_ERRORS)


async def _run_via_anthropic(prompt: str, *, role: str, model_id: str,
                              workspace: str | None, timeout_s: int,
                              session_id: str, thinking: str,
                              ) -> tuple[int, str, float, str | None]:
    """Dispatch one call through the Anthropic SDK.

    Extracted verbatim from run_via_provider so the OpenRouter path can reuse
    it as its fallback. Still routes through session_sdk to preserve the
    model_policy gate.
    """
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
            model=model_id,
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
                provider="anthropic", role=role, model=model_id,
                cost_usd=cost_f,
            )
        return rc_i, text or "", cost_f, None
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"anthropic_sdk_call_raised: {exc}"


async def run_via_provider(prompt: str, *, role: str,
                             task_class: str = "default",
                             timeout_s: int = 120,
                             workspace: str | None = None,
                             session_id: str = "",
                             thinking: str = "adaptive",
                             confidential: bool = False,
                             ) -> tuple[int, str, float, str | None]:
    """Single dispatch entry. Returns (rc, text, cost_usd, error_or_None).

    Picks (provider, model_id) via select_provider_model, then routes to
    the right SDK. Anthropic still fires through session_sdk to preserve
    the model_policy gate; OpenRouter goes through provider_openrouter.
    Tier-0 gathering roles walk the full free→paid→local chain with failover
    via tier0_runner; ``confidential=True`` forces that walk local-only.
    """
    pm = select_provider_model(role, task_class=task_class)

    # Tier-0 gathering lane (UNI-2212): the head-lane selection alone can't
    # fail over, so run the full resolved chain. Inert for every non-tier0
    # role today (no role maps to tier0 until the lane is activated).
    if pm.tier == "tier0":
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
            _record_cost_safe(
                provider=r.provider or "tier0", role=role,
                model=r.model_id or "", cost_usd=r.cost_usd,
            )
        return (0 if r.ok else 1), r.text, r.cost_usd, r.error

    # claude --print path ($0 marginal under Max plan)
    if pm.provider == "claude_print":
        rc, text, cost, err = await _run_via_claude_print(
            prompt, timeout_s=timeout_s,
        )
        if rc == 0:
            _record_cost_safe(
                provider="claude_print", role=role, model=pm.model_id,
                cost_usd=cost,
            )
        return rc, text, cost, err

    if pm.provider == "anthropic":
        return await _run_via_anthropic(
            prompt, role=role, model_id=pm.model_id, workspace=workspace,
            timeout_s=timeout_s, session_id=session_id, thinking=thinking,
        )

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

    # OpenRouter is tried FIRST, so it needs a second. Fall back to the capped
    # Anthropic key only when OpenRouter genuinely cannot serve the request.
    error = result[3] if len(result) > 3 else None
    if _openrouter_cannot_serve(error):
        fallback = _anthropic_fallback_model(pm.tier)
        if fallback:
            log.warning(
                "provider_router: openrouter:%s unavailable for role=%s (%s) — "
                "falling back to anthropic:%s",
                pm.model_id, role, error, fallback,
            )
            return await _run_via_anthropic(
                prompt, role=role, model_id=fallback, workspace=workspace,
                timeout_s=timeout_s, session_id=session_id, thinking=thinking,
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
    "is_anthropic", "is_openrouter", "is_ollama", "is_claude_print",
    "run_secondary_research_pass",
]


# ── nex-n2-pro:free secondary research pass (trial until 2026-06-25) ─────────
# REMOVE AFTER 2026-06-25 or if NEX_N2_FREE_UNTIL has passed — see provider_nex_n2.py.

async def run_secondary_research_pass(
    prompt: str,
    *,
    role: str = "research",
    timeout_s: int = 120,
    max_tokens: int = 8192,
    session_id: str = "",
    history: list | None = None,
    fallback_text: str = "",
) -> tuple[str, list]:
    """Run a secondary research/suggestion pass via nex-n2-pro:free.

    This is additive — it enriches an existing primary result with a second
    model's perspective.  It never replaces the primary model.

    Returns (secondary_text, reasoning_details).  On any error (disabled,
    rate-limited, network failure) returns (fallback_text, []) so the caller's
    primary path is unaffected.

    Example usage in a board meeting or research phase:
        primary_rc, primary_text, *_ = await run_via_provider(prompt, role="board")
        secondary_text, reasoning = await run_secondary_research_pass(
            prompt, role="board", fallback_text="",
        )
        # Use secondary_text as a second opinion alongside primary_text.
    """
    try:
        import sys as _sys  # noqa: PLC0415
        nex_n2 = _sys.modules.get("app.server.provider_nex_n2")
        if nex_n2 is None:
            from . import provider_nex_n2 as nex_n2  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("provider_router: nex_n2 import failed — %s", exc)
        return fallback_text, []

    return await nex_n2.research_pass(
        prompt,
        role=role,
        timeout_s=timeout_s,
        max_tokens=max_tokens,
        session_id=session_id,
        history=history,
        fallback_text=fallback_text,
    )


# ── Synchronous wrapper (RA-3003 consolidation) ─────────────────────────────

def run_via_provider_blocking(
    prompt: str,
    role: str,
    timeout_s: int = 120,
    *,
    log=None,
) -> tuple[int, str, float, str | None, ProviderModel]:
    """Sync wrapper around run_via_provider — safe from any context.

    Detects whether an event loop is already running. If yes (e.g.
    called from inside an async cron handler), delegates to a worker
    thread so asyncio.run() doesn't clash with the current loop. If no
    loop is running (e.g. called from a script `__main__`), uses
    asyncio.run() directly.

    The optional `log` callback is invoked with the resolved
    ProviderModel before the call fires, mirroring the
    cron_fire_agents.py helper signature it replaces.

    Returns (rc, text, cost_usd, error, ProviderModel) — same shape as
    the per-file _run_provider_call_blocking helpers it consolidates.

    Consolidates duplicate copies that lived in:
      app/server/triage.py
      app/server/agents/feedback_loop.py
      app/server/cron_fire_agents.py
      swarm/portfolio_pulse_synthesis.py
    """
    import asyncio  # noqa: PLC0415
    import concurrent.futures  # noqa: PLC0415

    pm = select_provider_model(role)
    if log is not None:
        try:
            log.debug("provider_router: role=%s provider=%s model=%s tier=%s",
                      role, pm.provider, pm.model_id, pm.tier)
        except Exception:  # noqa: BLE001 — log failure must not break the call
            pass

    async def _go() -> tuple[int, str, float, str | None]:
        return await run_via_provider(prompt=prompt, role=role, timeout_s=timeout_s)

    try:
        # If there's a running loop, we're in async context — delegate to a thread
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            rc, text, cost, error = ex.submit(asyncio.run, _go()).result(timeout=timeout_s + 5)
    except RuntimeError:
        # No running loop — safe to use asyncio.run directly
        rc, text, cost, error = asyncio.run(_go())
    return rc, text, cost, error, pm
