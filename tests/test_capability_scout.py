from __future__ import annotations

import json
from pathlib import Path

from scripts import capability_scout


def _projects_file(tmp_path: Path) -> Path:
    p = tmp_path / "projects.json"
    p.write_text(json.dumps({
        "projects": [
            {
                "id": "pi-dev-ops",
                "repo": "CleanExpo/Pi-Dev-Ops",
                "linear_project_name": "Pi Dev Ops",
                "stack": ["FastAPI", "Next.js", "Python", "TypeScript"],
            },
            {
                "id": "restoreassist",
                "repo": "CleanExpo/RestoreAssist",
                "linear_project_name": "RestoreAssist Compliance Platform",
                "stack": ["Next.js", "TypeScript", "Supabase"],
            },
        ]
    }), encoding="utf-8")
    return p


def test_load_project_profiles_builds_keywords(tmp_path):
    profiles = capability_scout.load_project_profiles(_projects_file(tmp_path))

    pi = next(p for p in profiles if p.project_id == "pi-dev-ops")
    ra = next(p for p in profiles if p.project_id == "restoreassist")

    assert "agent" in pi.keywords
    assert "python" in pi.keywords
    assert "compliance" in ra.keywords
    assert "supabase" in ra.keywords


def test_score_discovery_matches_projects_and_capability(tmp_path):
    profiles = capability_scout.load_project_profiles(_projects_file(tmp_path))
    discovery = capability_scout.Discovery(
        title="open-source autonomous coding agent with MCP workflow evals",
        url="https://github.com/example/agent",
        source_type="github",
        summary="An agent framework for Python tools, verification, and workflow orchestration.",
        metadata={"stars": 1400, "language": "Python"},
    )

    candidate = capability_scout.score_discovery(discovery, profiles, today="2026-06-16")

    assert candidate is not None
    assert candidate.relevance_score >= 70
    assert "pi-dev-ops" in candidate.project_matches
    assert candidate.capability_type in {"agent_runtime", "evals", "mcp_connector"}
    assert candidate.maturity == "adoptable"
    assert candidate.recommended_action == "create sandbox spike and draft skill candidate"


def test_low_signal_unmatched_discovery_is_filtered(tmp_path):
    profiles = capability_scout.load_project_profiles(_projects_file(tmp_path))
    discovery = capability_scout.Discovery(
        title="gardening calendar for spring bulbs",
        url="https://example.com/garden",
        source_type="arxiv",
        summary="A paper about planting flowers.",
    )

    assert capability_scout.score_discovery(discovery, profiles) is None


def test_build_candidates_sorts_by_score(tmp_path):
    profiles = capability_scout.load_project_profiles(_projects_file(tmp_path))
    discoveries = [
        capability_scout.Discovery(
            title="small RAG note",
            url="https://example.com/rag",
            source_type="arxiv",
            summary="retrieval augmented generation for documents",
        ),
        capability_scout.Discovery(
            title="CleanExpo/mcp-agent-workflow",
            url="https://github.com/CleanExpo/mcp-agent-workflow",
            source_type="github",
            summary="MCP agent orchestration eval workflow in Python",
            metadata={"stars": 2000},
        ),
    ]

    candidates = capability_scout.build_candidates(discoveries, profiles, today="2026-06-16")

    assert len(candidates) == 2
    assert candidates[0].relevance_score >= candidates[1].relevance_score
    assert candidates[0].source_type == "github"


def test_write_brain_outputs_creates_report_manifest_and_sources(tmp_path):
    brain = tmp_path / "2nd-brain"
    candidate = capability_scout.CapabilityCandidate(
        title="CleanExpo/mcp-agent-workflow",
        source_url="https://github.com/CleanExpo/mcp-agent-workflow",
        source_type="github",
        summary="MCP agent orchestration eval workflow in Python",
        project_matches=("pi-dev-ops",),
        capability_type="agent_runtime",
        maturity="adoptable",
        implementation_effort="3-7 days sandbox",
        expected_leverage="high",
        risk="dependency and security review required",
        recommended_action="create sandbox spike and draft skill candidate",
        relevance_score=91,
        discovered_at="2026-06-16",
    )

    result = capability_scout.write_brain_outputs([candidate], brain, today="2026-06-16")

    report = Path(result["report_path"])
    manifest = Path(result["manifest_path"])
    assert report.exists()
    assert manifest.exists()
    assert result["source_count"] == 1
    assert "Capability Scout Report" in report.read_text(encoding="utf-8")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["candidate_count"] == 1
    source_path = Path(data["source_paths"][0])
    assert source_path.exists()
    assert "type: capability-source" in source_path.read_text(encoding="utf-8")
