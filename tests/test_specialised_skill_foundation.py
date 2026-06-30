from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "specialised_skill_foundation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("specialised_skill_foundation", SCRIPT_PATH)
    assert spec and spec.loader, f"unable to import {SCRIPT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["specialised_skill_foundation"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_slugify_skill_name_is_filesystem_safe():
    mod = _load_module()

    assert mod.slugify_skill_name("CCW Service Department Busy Campaign!") == "ccw-service-department-busy-campaign"
    assert mod.slugify_skill_name("  Nexus / Evidence Ledger  ") == "nexus-evidence-ledger"


def test_build_foundation_packet_is_approval_gated_and_anthropic_shaped(tmp_path: Path):
    mod = _load_module()
    existing_manifest = tmp_path / "agentskills.json"
    existing_manifest.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "id": "evidence-ledger",
                        "description": "Create evidence ledgers for shipped work.",
                        "path": "skills/evidence-ledger/SKILL.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    packet = mod.build_foundation_packet(
        name="Nexus Evidence Ledger",
        trigger="When a run needs proof paths, command outputs, and acceptance evidence before handoff.",
        evidence=["lesson-1", "obsidian://Sketches/05-nexus-skills-os"],
        repo_root=tmp_path,
        existing_manifest_path=existing_manifest,
    )

    assert packet["status"] == "need_approval"
    assert packet["blocked_reason"] == "human_review_required_before_live_skill_mutation"
    assert packet["proposed_skill_name"] == "nexus-evidence-ledger"
    assert packet["recommended_action"] == "amend_existing_skill"
    assert packet["nearest_existing_skill"]["id"] == "evidence-ledger"
    assert packet["draft_skill_path"] == "skills/nexus-evidence-ledger/SKILL.md"
    assert "description:" in packet["draft_skill_md"]
    assert "when_to_use:" in packet["draft_skill_md"]
    assert "disable-model-invocation: true" in packet["draft_skill_md"]
    assert "allowed-tools:" in packet["draft_skill_md"]
    assert "## Evidence Foundation" in packet["draft_skill_md"]
    assert "No production DB writes" in packet["draft_skill_md"]


def test_write_packet_creates_proposal_not_live_skill(tmp_path: Path):
    mod = _load_module()
    packet = mod.build_foundation_packet(
        name="Supabase Operator",
        trigger="When a task needs Supabase schema or REST checks without production mutation.",
        evidence=["lesson-2"],
        repo_root=tmp_path,
    )

    out = mod.write_foundation_packet(packet, tmp_path)

    assert out.exists()
    assert out.parent == tmp_path / ".harness" / "skill-foundations"
    assert not (tmp_path / "skills" / "supabase-operator" / "SKILL.md").exists()

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["status"] == "need_approval"
    assert saved["approval_contract"]["may_write_live_skill"] is False
    assert saved["approval_contract"]["approval_required_to_create"] is True
