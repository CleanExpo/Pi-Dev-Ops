"""Prove-It Gate — slice 1 (RA-7014).

Golden-dataset regression eval for the model router. This is the "code-checkable
failure indicator" half of the Prove-It Gate: deterministic assertions over
select_provider_model(role), no LLM judge needed. It runs as a NON-BLOCKING CI
check first (see .github/workflows/prove_it_evals.yml); it is flipped to a blocking
tao-loop gate only after the judged/calibrated slices land.

Pilot target is provider_router (in-repo, deterministic, and Cap 1's own surface) —
chosen over the sketch's pm-core, which does not live in this repo.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

# Force the cheap tier to skip the ollama-reachability probe so cheap-role cases
# are deterministic in CI (no network). Set before importing the router.
os.environ.setdefault("TAO_CHEAP_PROVIDER", "openrouter")

from app.server.provider_router import (  # noqa: E402
    is_anthropic,
    select_provider_model,
)

_GOLDEN = Path(__file__).parent / "golden" / "provider_router_roles.yaml"
_CASES = yaml.safe_load(_GOLDEN.read_text())["cases"]


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["role"])
def test_router_matches_golden(case: dict) -> None:
    pm = select_provider_model(case["role"])

    assert pm.tier == case["tier"], (
        f"{case['role']}: tier {pm.tier!r} != expected {case['tier']!r}"
    )

    if case.get("not_anthropic"):
        assert not is_anthropic(pm), (
            f"{case['role']}: cheap-tier role must not route to Anthropic, got {pm!r}"
        )
    else:
        assert pm.provider == case["provider"], (
            f"{case['role']}: provider {pm.provider!r} != {case['provider']!r}"
        )
        assert pm.model_id == case["model_id"], (
            f"{case['role']}: model {pm.model_id!r} != {case['model_id']!r}"
        )


def test_unmapped_role_never_escalates_to_top() -> None:
    """Cost guard: an unknown role must never silently route to the top tier."""
    pm = select_provider_model("definitely_not_a_registered_role")
    assert pm.tier != "top", f"unmapped role escalated to top tier: {pm!r}"
