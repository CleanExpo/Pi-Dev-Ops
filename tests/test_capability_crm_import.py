from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import capability_crm_import


def _proposal(**overrides):
    data = {
        "title": "Review capability: microsoft/agent-framework",
        "description": "Review external AI capability with approval gates.",
        "status": "blocked",
        "priority": "high",
        "assignee_name": "Phill approval",
        "tags": [
            "capability-scout",
            "approval-required",
            "unite-crm",
            "second-brain",
            "hermes-intake",
            "agent_runtime",
            "github",
        ],
        "obsidian_path": "Sources/2026-06-16-capability-microsoft-agent-framework.md",
        "source_url": "https://github.com/microsoft/agent-framework",
        "project_matches": ["pi-dev-ops", "unite-group"],
        "capability_type": "agent_runtime",
        "relevance_score": 96,
        "hermes_lane": "engineering",
    }
    data.update(overrides)
    return data


def test_load_manifest_crm_tasks(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"crm_tasks": [_proposal()]}), encoding="utf-8")

    proposals = capability_crm_import.load_manifest_or_jsonl(manifest)

    assert len(proposals) == 1
    assert proposals[0]["status"] == "blocked"


def test_load_manifest_bridge_path(tmp_path: Path):
    bridge = tmp_path / "bridge.jsonl"
    bridge.write_text(json.dumps(_proposal()) + "\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"crm_bridge_path": str(bridge)}), encoding="utf-8")

    proposals = capability_crm_import.load_manifest_or_jsonl(manifest)

    assert proposals[0]["obsidian_path"].startswith("Sources/")


def test_validate_proposals_rejects_non_blocked_status():
    with pytest.raises(capability_crm_import.IntakeError, match="status_not_blocked"):
        capability_crm_import.validate_proposals([_proposal(status="ready")])


def test_validate_proposals_requires_approval_tags():
    with pytest.raises(capability_crm_import.IntakeError, match="missing_required_tags"):
        capability_crm_import.validate_proposals([_proposal(tags=["capability-scout"])])


def test_main_dry_run_json(tmp_path: Path, capsys):
    bridge = tmp_path / "bridge.jsonl"
    bridge.write_text(json.dumps(_proposal()) + "\n", encoding="utf-8")

    code = capability_crm_import.main([str(bridge), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "dry-run"
    assert payload["proposal_count"] == 1
