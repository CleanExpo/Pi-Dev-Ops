from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm.hermes_production_unit import build_packet, render_markdown, split_issues, write_packet  # noqa: E402
from swarm.hermes_production_unit import ProductionIssue  # noqa: E402


def _issues():
    return [
        {
            "id": "RA-1",
            "title": "Fix RestoreAssist CI deploy failure",
            "priority": {"value": 1},
            "project": "RestoreAssist",
            "url": "https://linear.app/x/RA-1",
        },
        {
            "id": "RA-2",
            "title": "Audit stale Linear tickets and verify evidence",
            "priority": 2,
            "project": "Pi-Dev-Ops",
        },
        {
            "id": "RA-3",
            "title": "Rotate leaked billing and API secrets",
            "priority": 1,
            "project": "Pi-Dev-Ops",
        },
    ]


def test_split_issues_routes_builds_and_verification_separately():
    issues = [ProductionIssue.from_mapping(item) for item in _issues()]

    delivery, verification = split_issues(issues)

    assert [issue.identifier for issue in delivery] == ["RA-1"]
    assert [issue.identifier for issue in verification] == ["RA-3", "RA-2"]


def test_build_packet_contains_two_child_agents_and_contracts():
    now = datetime(2026, 6, 18, 7, 0, tzinfo=timezone.utc)

    packet = build_packet(_issues(), now=now)

    assert packet.lead == "Margot"
    assert packet.generated_at == "2026-06-18T07:00:00+00:00"
    assert [child.agent_id for child in packet.children] == [
        "hermes-child-delivery-1",
        "hermes-child-verification-1",
    ]
    assert packet.children[0].assigned_issues[0].identifier == "RA-1"
    assert "Claim exactly one issue" in packet.claim_contract[0]
    assert any("Do not mark Linear Done" in item for item in packet.merge_contract)


def test_render_markdown_includes_human_gate_and_machine_json():
    packet = build_packet(_issues(), now=datetime(2026, 6, 18, tzinfo=timezone.utc))

    text = render_markdown(packet)

    assert "# Margot-Led Hermes Linear Production Unit" in text
    assert "human approval" in text.lower()
    assert "hermes-child-delivery-1" in text
    assert "```json" in text


def test_write_packet_outputs_markdown_and_json(tmp_path):
    packet = build_packet(_issues(), now=datetime(2026, 6, 18, tzinfo=timezone.utc))

    md_path, json_path = write_packet(packet, tmp_path)

    assert md_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["lead"] == "Margot"
    assert payload["children"][1]["lane"] == "verification"
