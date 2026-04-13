"""
test_budget.py — Unit tests for budget.py AUTONOMY_BUDGET mapper.

Covers:
- Anchor values returned exactly at boundary points
- Clamping below min anchor and above max anchor
- Linear interpolation of threshold, retries, timeout between anchors
- Model switching at 50% midpoint between anchors
- describe_budget returns correct string format
- Edge cases: 0, negative, very large values
"""
import pytest
from app.server.budget import budget_to_params, describe_budget


# ── Anchor boundary tests ──────────────────────────────────────────────────────

def test_anchor_10_min():
    p = budget_to_params(10)
    assert p["eval_threshold"] == 7.5
    assert p["max_retries"] == 1
    assert p["model"] == "haiku"
    assert p["generator_timeout_secs"] == 480
    assert p["budget_minutes"] == 10


def test_anchor_30_min():
    p = budget_to_params(30)
    assert p["eval_threshold"] == 8.0
    assert p["max_retries"] == 2
    assert p["model"] == "sonnet"
    assert p["generator_timeout_secs"] == 1500


def test_anchor_60_min():
    p = budget_to_params(60)
    assert p["eval_threshold"] == 8.5
    assert p["max_retries"] == 3
    assert p["model"] == "sonnet"
    assert p["generator_timeout_secs"] == 3000


def test_anchor_120_min():
    p = budget_to_params(120)
    assert p["eval_threshold"] == 9.0
    assert p["max_retries"] == 4
    assert p["model"] == "opus"
    assert p["generator_timeout_secs"] == 6000


def test_anchor_240_min():
    p = budget_to_params(240)
    assert p["eval_threshold"] == 9.5
    assert p["max_retries"] == 5
    assert p["model"] == "opus"
    assert p["generator_timeout_secs"] == 12000


# ── Clamping tests ─────────────────────────────────────────────────────────────

def test_clamps_below_minimum():
    """Values below 10 min should return the 10-min anchor."""
    p = budget_to_params(1)
    assert p["model"] == "haiku"
    assert p["eval_threshold"] == 7.5
    assert p["budget_minutes"] == 1  # input echoed, not clamped


def test_zero_clamped_to_minimum_anchor():
    """0 min is clamped to 1 (max(1, int(0))) then to minimum anchor."""
    p = budget_to_params(0)
    assert p["model"] == "haiku"


def test_negative_clamped():
    p = budget_to_params(-50)
    assert p["model"] == "haiku"
    assert p["eval_threshold"] == 7.5


def test_clamps_above_maximum():
    """Values above 240 min should return the 240-min anchor."""
    p = budget_to_params(999)
    assert p["model"] == "opus"
    assert p["eval_threshold"] == 9.5
    assert p["budget_minutes"] == 999  # input echoed


# ── Interpolation tests ────────────────────────────────────────────────────────

def test_midpoint_10_30_threshold():
    """At 20 min (midpoint of 10-30), threshold should be midpoint of 7.5-8.0."""
    p = budget_to_params(20)
    assert p["eval_threshold"] == 7.8  # 7.5 + 0.5*(8.0-7.5) = 7.75 → rounded to 7.8


def test_midpoint_10_30_model_still_lower():
    """At exactly 20 min (t=0.5), model switches to higher anchor (sonnet)."""
    p = budget_to_params(20)
    assert p["model"] == "sonnet"  # t=0.5 → switches to hi_mdl


def test_just_before_midpoint_uses_lower_model():
    """At 19 min in 10-30 range (t=0.45), model stays at lower (haiku)."""
    p = budget_to_params(19)
    assert p["model"] == "haiku"


def test_just_after_midpoint_uses_higher_model():
    """At 21 min in 10-30 range (t=0.55), model upgrades to sonnet."""
    p = budget_to_params(21)
    assert p["model"] == "sonnet"


def test_interpolated_timeout_is_between_anchors():
    """Timeout at any midpoint should be between the two anchor timeouts."""
    p20 = budget_to_params(20)  # Between 10 (480s) and 30 (1500s)
    assert 480 < p20["generator_timeout_secs"] < 1500


def test_interpolated_retries_at_midpoint():
    """At t=0.5 between 10 (retries=1) and 30 (retries=2), should be 2 (round(1.5)=2)."""
    p = budget_to_params(20)
    assert p["max_retries"] == 2


def test_all_required_keys_present():
    """Every params dict must have all 5 required keys."""
    required = {"eval_threshold", "max_retries", "model", "generator_timeout_secs", "budget_minutes"}
    for minutes in [1, 10, 20, 30, 60, 90, 120, 180, 240, 300]:
        p = budget_to_params(minutes)
        assert required.issubset(p.keys()), f"Missing keys for budget={minutes}: {required - p.keys()}"


# ── describe_budget tests ──────────────────────────────────────────────────────

def test_describe_budget_contains_all_fields():
    p = budget_to_params(60)
    desc = describe_budget(p)
    assert "budget=60min" in desc
    assert "model=sonnet" in desc
    assert "threshold=8.5/10" in desc
    assert "retries=3" in desc
    assert "timeout=50min" in desc


def test_describe_budget_haiku():
    p = budget_to_params(10)
    desc = describe_budget(p)
    assert "model=haiku" in desc
    assert "timeout=8min" in desc
