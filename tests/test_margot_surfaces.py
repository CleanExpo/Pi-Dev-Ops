"""Margot per-project surface SSOT tests."""
from __future__ import annotations

from pathlib import Path
import json


def test_margot_identity_projects_include_bubble_brands():
    path = Path(__file__).resolve().parents[1] / ".harness" / "margot" / "assets" / "margot_identity.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    projects = data["projects"]
    for slug in ("unite-group", "restoreassist", "carsi"):
        assert slug in projects, f"missing {slug} in margot_identity.json"


def test_tenant_scope_locks_cover_bubble_brands():
    from swarm.margot_bot import _TENANT_SCOPE_LOCKS

    for slug in ("unite-group", "restoreassist", "carsi"):
        assert slug in _TENANT_SCOPE_LOCKS
        assert len(_TENANT_SCOPE_LOCKS[slug]) > 40


def test_margot_turn_carries_tenant_id():
    from swarm.margot_bot import MargotTurn

    turn = MargotTurn(chat_id="x", user_text="hi", tenant_id="carsi")
    assert turn.tenant_id == "carsi"


def test_build_prompt_injects_scope_for_tenant():
    from swarm.margot_bot import build_prompt

    prompt = build_prompt(
        user_text="hello",
        history=[],
        context={},
        tenant_id="carsi",
    )
    assert "Project scope (mandatory)" in prompt
    assert "CARSI" in prompt


def test_build_prompt_omits_scope_for_pi_ceo_default():
    from swarm.margot_bot import build_prompt

    prompt = build_prompt(
        user_text="hello",
        history=[],
        context={},
        tenant_id="pi-ceo",
    )
    assert "Project scope (mandatory)" not in prompt
