"""A quality-critical role routed to the cheap model must leave a record.

ROLE_TIER declares planner/orchestrator/board "top — quality-critical reasoning" and
generator/evaluator "mid — production-quality output". A per-role TAO_MODEL_<ROLE> override
is resolution step 1 and the tier mapping is step 2, so an override silently replaces the
tier decision.

Production has every one of those roles overridden to the cheap-tier model, and it went
unnoticed for months: model_policy reads config.yaml (a different path), and provider_router
states at its top that it does not enforce OPUS_ALLOWED_ROLES. That gate is a ceiling
anyway — it only asks whether something is opus when it should not be, never whether a
model is good enough for the role.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.server import model_policy, provider_router


CHEAP = "~moonshotai/kimi-latest"


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "model-policy-violations.jsonl"
    monkeypatch.setattr(model_policy, "VIOLATIONS_PATH", path)
    monkeypatch.setenv("TAO_CHEAP_REMOTE_MODEL", CHEAP)
    return path


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


@pytest.mark.parametrize("role", ["planner", "orchestrator", "board", "generator", "evaluator"])
def test_quality_critical_role_on_cheap_model_is_recorded(
    role: str, ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This is production's exact configuration, role by role."""
    monkeypatch.setenv(provider_router._env_role_key(role), f"openrouter:{CHEAP}")

    resolved = provider_router.select_provider_model(role)

    # Was `== CHEAP`, asserting the downgrade was honoured. That documented a
    # deliberate choice to observe rather than gate — and observing did not stop
    # production answering every one of these roles with the cheap model. The
    # override is now corrected to the tier default. The recording assertions
    # below are unchanged and still the point of this test: correcting must not
    # silence the ledger, or the wrong env var would live forever unseen.
    assert resolved.model_id != CHEAP
    assert resolved.source == "tier_downgrade_corrected"
    recorded = _records(ledger)
    assert len(recorded) == 1, f"no record written for {role}"
    assert recorded[0]["role"] == role
    assert CHEAP in recorded[0]["granted"]
    assert "bypassed by a per-role override" in recorded[0]["reason"]


def test_cheap_tier_role_on_cheap_model_is_not_recorded(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control. A cheap-tier role on the cheap model is correct, not a downgrade.

    Without this, a check that recorded everything would look identical to one that
    recorded the right thing.
    """
    monkeypatch.setenv(provider_router._env_role_key("intent_classify"), f"openrouter:{CHEAP}")

    provider_router.select_provider_model("intent_classify")

    assert _records(ledger) == []


def test_top_role_on_a_non_cheap_model_is_not_recorded(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overriding a top role is fine when it is not a downgrade to the cheap tier."""
    monkeypatch.setenv(provider_router._env_role_key("planner"), "anthropic:claude-opus-4")

    provider_router.select_provider_model("planner")

    assert _records(ledger) == []


def test_recording_failure_never_breaks_resolution(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observability must not be able to take down model selection."""
    monkeypatch.setattr(model_policy, "VIOLATIONS_PATH", Path("/nonexistent-dir/x/y.jsonl"))
    monkeypatch.setenv(provider_router._env_role_key("planner"), f"openrouter:{CHEAP}")

    resolved = provider_router.select_provider_model("planner")

    # The guarantee is unchanged — a broken ledger still yields a usable model.
    # Only the expected value moves, because the downgrade is now corrected
    # rather than honoured. Asserting a non-empty model_id as well, so this
    # cannot pass on an empty string if resolution ever half-fails.
    assert resolved.model_id != CHEAP
    assert resolved.model_id
