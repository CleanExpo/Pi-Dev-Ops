from __future__ import annotations

import json
from pathlib import Path

from scripts import capability_crm_import, idea_expansion


def test_expand_idea_generates_strategic_context_not_literal_only():
    expansion = idea_expansion.expand_idea(
        "Build the command-center Capability Approval panel",
        today="2026-06-16",
    )

    assert expansion.title == "Build the command-center Capability Approval panel"
    assert len(expansion.research_lanes) >= 6
    assert "wider capability" in expansion.strategic_read
    assert any(
        "external products" in item and "papers" in item
        for item in expansion.adjacent_opportunities
    )
    assert any("research" in item.lower() for item in expansion.adjacent_opportunities)
    assert {lane.lane for lane in expansion.research_lanes} >= {
        "github",
        "huggingface",
        "papers",
        "products",
        "security",
        "implementation",
    }
    assert len(expansion.crm_tasks) == 3
    capability_crm_import.validate_proposals(list(expansion.crm_tasks))


def test_write_outputs_creates_brain_packet_and_crm_bridge(tmp_path: Path):
    expansion = idea_expansion.expand_idea(
        "System should expand my ideas before implementation",
        today="2026-06-16",
    )

    result = idea_expansion.write_outputs(expansion, tmp_path)

    idea_path = Path(result["idea_path"])
    research_path = Path(result["research_path"])
    decision_path = Path(result["decision_path"])
    crm_bridge_path = Path(result["crm_bridge_path"])
    manifest_path = Path(result["manifest_path"])

    assert idea_path.exists()
    assert research_path.exists()
    assert decision_path.exists()
    assert crm_bridge_path.exists()
    assert manifest_path.exists()
    assert "Strategic Read" in idea_path.read_text(encoding="utf-8")
    assert "Research Lanes" in research_path.read_text(encoding="utf-8")
    assert "Safety Boundary" in decision_path.read_text(encoding="utf-8")
    assert len(capability_crm_import.load_manifest_or_jsonl(crm_bridge_path)) == 3

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["crm_task_count"] == 3
    assert manifest["crm_bridge_path"] == str(crm_bridge_path)


def test_main_dry_run_json_does_not_write(tmp_path: Path, capsys):
    code = idea_expansion.main([
        "Expand",
        "literal",
        "ideas",
        "--brain-root",
        str(tmp_path),
        "--dry-run",
        "--json",
    ])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["expansion"]["crm_tasks"]
    assert not (tmp_path / "Ideas").exists()
