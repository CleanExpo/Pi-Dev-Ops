"""A per-role override may not downgrade a quality-critical role to the cheap model.

The prior change made the downgrade OBSERVABLE. Observability did not stop it:
production still answered every planner, orchestrator, board, generator and
evaluator call with the cheap model, and the ledger simply recorded that it was
happening. These tests pin the correction — the role now falls back to its tier
default instead of honouring the override.

Correction rather than refusal is deliberate. Raising would take production down
over a config that has been live for months; correcting keeps every call served
while ending the downgrade.

The scope is deliberately narrow, and the negative controls below are the point:
only an override naming the CONFIGURED CHEAP MODEL for a top/mid role is
corrected. Any other override is an operator choosing a specific capable model,
which is legitimate and must pass through untouched.
"""

import importlib

import pytest


@pytest.fixture
def router(monkeypatch, tmp_path):
    """Fresh router module with a known cheap model and an isolated ledger."""
    monkeypatch.setenv("TAO_CHEAP_REMOTE_MODEL", "cheap/tiny-model")
    monkeypatch.setenv("TAO_TOP_MODEL", "claude-opus-4-5")
    monkeypatch.setenv("TAO_MID_MODEL", "claude-sonnet-4-6")
    import app.server.provider_router as pr
    importlib.reload(pr)

    import app.server.model_policy as mp
    monkeypatch.setattr(mp, "VIOLATIONS_PATH", tmp_path / "violations.jsonl")
    return pr


# Production's actual configuration: every quality-critical role pinned to the
# cheap model via a per-role override.
QUALITY_CRITICAL = ["planner", "orchestrator", "board", "generator", "evaluator"]


@pytest.mark.parametrize("role", QUALITY_CRITICAL)
def test_cheap_override_is_corrected_to_tier_default(router, monkeypatch, role):
    monkeypatch.setenv(router._env_role_key(role), "openrouter:cheap/tiny-model")

    pm = router.select_provider_model(role)

    assert pm.model_id != "cheap/tiny-model", (
        f"{role} is still answered by the cheap model — the override was honoured"
    )
    assert pm.source == "tier_downgrade_corrected"
    expected_tier = router.ROLE_TIER[role]
    assert pm.tier == expected_tier
    assert pm.model_id == ("claude-opus-4-5" if expected_tier == "top" else "claude-sonnet-4-6")


@pytest.mark.parametrize("role", QUALITY_CRITICAL)
def test_the_downgrade_is_still_recorded_when_corrected(router, monkeypatch, role):
    """Correcting must not silence the ledger.

    The operator still has a wrong env var set; if correction hid it, the
    misconfiguration would live forever because nothing would ever surface it.
    """
    monkeypatch.setenv(router._env_role_key(role), "openrouter:cheap/tiny-model")

    router.select_provider_model(role)

    import app.server.model_policy as mp
    assert mp.VIOLATIONS_PATH.exists(), "the correction swallowed the record"
    assert role in mp.VIOLATIONS_PATH.read_text()


# ── Negative controls — these must NOT be corrected ─────────────────────────

def test_a_cheap_role_on_the_cheap_model_is_left_alone(router, monkeypatch):
    """`monitor` is declared cheap. The cheap model is the CORRECT answer."""
    monkeypatch.setenv(router._env_role_key("monitor"), "openrouter:cheap/tiny-model")

    pm = router.select_provider_model("monitor")

    assert pm.model_id == "cheap/tiny-model"
    assert pm.source == "env_role_override"


def test_a_top_role_on_a_different_model_is_left_alone(router, monkeypatch):
    """An operator pinning a specific capable model is a legitimate decision.

    Without this, the change would be a general-purpose model policy rather
    than a downgrade guard, and would override deliberate routing choices.
    """
    monkeypatch.setenv(router._env_role_key("planner"), "anthropic:claude-opus-4-8")

    pm = router.select_provider_model("planner")

    assert pm.model_id == "claude-opus-4-8"
    assert pm.source == "env_role_override"


def test_no_override_still_uses_the_tier_default(router):
    pm = router.select_provider_model("planner")
    assert pm.source == "env_tier_default"
    assert pm.model_id == "claude-opus-4-5"


def test_no_cheap_model_configured_disables_the_guard(router, monkeypatch):
    """With TAO_CHEAP_REMOTE_MODEL unset there is no cheap model to compare to.

    Guessing one would let the guard fire on an arbitrary model name.
    """
    monkeypatch.delenv("TAO_CHEAP_REMOTE_MODEL", raising=False)
    monkeypatch.setenv(router._env_role_key("planner"), "openrouter:cheap/tiny-model")

    pm = router.select_provider_model("planner")

    assert pm.model_id == "cheap/tiny-model"
    assert pm.source == "env_role_override"


def test_predicate_is_shared_by_recorder_and_correction(router):
    """Both paths must consult one predicate.

    They were two copies of the same condition for one commit — the shape of bug
    where the ledger reports a downgrade the router silently allows, or vice
    versa.
    """
    assert router._is_tier_downgrade("planner", "cheap/tiny-model") is True
    assert router._is_tier_downgrade("monitor", "cheap/tiny-model") is False
    assert router._is_tier_downgrade("planner", "claude-opus-4-5") is False


def test_a_broken_ledger_cannot_break_model_selection(router, monkeypatch):
    """Recording is fire-and-forget; a failed write must not deny a model."""
    import app.server.model_policy as mp
    monkeypatch.setattr(mp, "VIOLATIONS_PATH", tmp := __import__("pathlib").Path("/nonexistent-dir/x.jsonl"))
    assert tmp  # referenced so the assignment is not mistaken for dead code
    monkeypatch.setenv(router._env_role_key("planner"), "openrouter:cheap/tiny-model")

    pm = router.select_provider_model("planner")

    assert pm.model_id == "claude-opus-4-5"
