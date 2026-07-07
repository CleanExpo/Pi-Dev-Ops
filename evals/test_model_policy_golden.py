"""Prove-It Gate (RA-7014) — golden regression eval for the model-selection gate.

Deterministic, code-checkable assertions over model_policy.select_model +
effort_for_role, including the security-critical Opus-allowlist downshift
(RA-1099). No LLM judge. Widens the blocking gate beyond provider_router to a
second, security-critical agent surface.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.server import model_policy as mp

_GOLDEN = Path(__file__).parent / "golden" / "model_policy_selection.yaml"
_DATA = yaml.safe_load(_GOLDEN.read_text())
_SELECTION = _DATA["selection"]
_ALLOWLIST = _DATA["allowlist"]


@pytest.mark.parametrize("case", _SELECTION, ids=lambda c: c["role"])
def test_role_resolves_to_expected_model_and_effort(case: dict) -> None:
    model = mp.select_model(case["role"])
    effort = mp.effort_for_role(case["role"])
    assert model == case["model"], f"{case['role']}: model {model!r} != {case['model']!r}"
    assert effort == case["effort"], f"{case['role']}: effort {effort!r} != {case['effort']!r}"


@pytest.mark.parametrize("case", _ALLOWLIST, ids=lambda c: f"{c['role']}+{c['requested']}")
def test_opus_allowlist_downshift(case: dict) -> None:
    """Security-critical: a role not in OPUS_ALLOWED_ROLES must be downshifted off opus."""
    granted = mp.select_model(case["role"], case["requested"])
    assert granted == case["granted"], (
        f"{case['role']} requesting {case['requested']}: got {granted!r}, "
        f"expected {case['granted']!r} — allowlist regression"
    )


def test_no_unlisted_role_silently_gets_opus() -> None:
    """A brand-new/unmapped role must never resolve to opus without an explicit request."""
    assert mp.select_model("a_totally_new_role_xyz") != "opus"
