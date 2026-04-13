"""
budget.py — RA-677: AUTONOMY_BUDGET single-knob pipeline configuration.

Maps a time budget (minutes) to a complete parameter set for the evaluator,
generator, and retry loop.  Values between anchor points are linearly
interpolated; model selection uses the lower anchor's model until the midpoint
between two adjacent anchors, then switches to the higher anchor's model.

Usage:
    from .budget import budget_to_params
    params = budget_to_params(60)
    # {'eval_threshold': 8.5, 'max_retries': 3, 'model': 'sonnet',
    #  'generator_timeout_secs': 3000, 'budget_minutes': 60}

Anchor table (matches RA-677 spec):
  Budget  eval_threshold  max_retries  model   timeout
   10 min       7.5           1        haiku      8 min
   30 min       8.0           2        sonnet    25 min
   60 min       8.5           3        sonnet    50 min
  120 min       9.0           4        opus     100 min
  240 min       9.5           5        opus     200 min
"""
from __future__ import annotations

# (minutes, eval_threshold, max_retries, model, generator_timeout_secs)
_BUDGET_ANCHORS: list[tuple[int, float, int, str, int]] = [
    ( 10, 7.5, 1, "haiku",   480),
    ( 30, 8.0, 2, "sonnet", 1500),
    ( 60, 8.5, 3, "sonnet", 3000),
    (120, 9.0, 4, "opus",   6000),
    (240, 9.5, 5, "opus",  12000),
]


def budget_to_params(minutes: int) -> dict:
    """Map AUTONOMY_BUDGET minutes to a full parameter dict.

    Parameters returned:
      eval_threshold         — float, replaces config.EVALUATOR_THRESHOLD
      max_retries            — int,   replaces config.EVALUATOR_MAX_RETRIES
      model                  — str,   generator model (haiku / sonnet / opus)
      generator_timeout_secs — int,   max wall-clock seconds for generator phase
      budget_minutes         — int,   echo of the input (for logging / display)
    """
    minutes = max(1, int(minutes))

    # Clamp to minimum anchor
    if minutes <= _BUDGET_ANCHORS[0][0]:
        m, thr, ret, mdl, tmo = _BUDGET_ANCHORS[0]
        return _pack(thr, ret, mdl, tmo, minutes)

    # Clamp to maximum anchor
    if minutes >= _BUDGET_ANCHORS[-1][0]:
        m, thr, ret, mdl, tmo = _BUDGET_ANCHORS[-1]
        return _pack(thr, ret, mdl, tmo, minutes)

    # Linear interpolation between adjacent anchors
    for i in range(len(_BUDGET_ANCHORS) - 1):
        lo_m, lo_thr, lo_ret, lo_mdl, lo_tmo = _BUDGET_ANCHORS[i]
        hi_m, hi_thr, hi_ret, hi_mdl, hi_tmo = _BUDGET_ANCHORS[i + 1]
        if lo_m <= minutes <= hi_m:
            t = (minutes - lo_m) / (hi_m - lo_m)
            threshold    = round(lo_thr + t * (hi_thr - lo_thr), 1)
            max_retries  = round(lo_ret + t * (hi_ret - lo_ret))
            timeout_secs = round(lo_tmo + t * (hi_tmo - lo_tmo))
            # Model: switch to the higher model when we are past the midpoint
            model = hi_mdl if t >= 0.5 else lo_mdl
            return _pack(threshold, max_retries, model, timeout_secs, minutes)

    # Unreachable — but satisfy type checker
    m, thr, ret, mdl, tmo = _BUDGET_ANCHORS[-1]
    return _pack(thr, ret, mdl, tmo, minutes)


def _pack(
    eval_threshold: float,
    max_retries: int,
    model: str,
    generator_timeout_secs: int,
    budget_minutes: int,
) -> dict:
    return {
        "eval_threshold": eval_threshold,
        "max_retries": max_retries,
        "model": model,
        "generator_timeout_secs": generator_timeout_secs,
        "budget_minutes": budget_minutes,
    }


def describe_budget(params: dict) -> str:
    """Human-readable one-liner for log output and dashboard display."""
    return (
        f"budget={params['budget_minutes']}min "
        f"model={params['model']} "
        f"threshold={params['eval_threshold']}/10 "
        f"retries={params['max_retries']} "
        f"timeout={params['generator_timeout_secs'] // 60}min"
    )
