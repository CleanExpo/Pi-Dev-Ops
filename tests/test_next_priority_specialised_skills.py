from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, rel: str):
    path = REPO_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_markdown_bloat_auditor_scores_and_writes_ranked_audit(tmp_path):
    mod = _load_module("markdown_bloat_audit", "scripts/markdown_bloat_audit.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Runtime\n\nKeep me short.\n", encoding="utf-8")
    plan = repo / "docs" / "superpowers" / "plans" / "huge-plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Huge\n" + "phase todo noise\n" * 320, encoding="utf-8")
    skill = repo / "skills" / "large" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: large\ndescription: big\n---\n" + "procedure\n" * 230, encoding="utf-8")
    harness = repo / ".harness" / "artefacts" / "old.md"
    harness.parent.mkdir(parents=True)
    harness.write_text("archived generated artifact\n" * 500, encoding="utf-8")

    report = mod.audit_markdown(repo, top=5)

    assert all(not item["path"].startswith(".harness/") for item in report)
    assert report[0]["path"] == "docs/superpowers/plans/huge-plan.md"
    assert report[0]["recommendation"] == "archive_compress"
    assert any(item["path"] == "skills/large/SKILL.md" and item["recommendation"] == "split_skill_references" for item in report)

    output = tmp_path / "audit.md"
    mod.write_audit(output, report)
    text = output.read_text(encoding="utf-8")
    assert "Markdown bloat audit" in text
    assert "huge-plan.md" in text


def test_skill_splitter_creates_router_and_reference_without_destroying_evidence(tmp_path):
    mod = _load_module("skill_splitter", "scripts/skill_splitter.py")
    skill_dir = tmp_path / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\nname: sample\ndescription: Use when sample.\n---\n"
        "# Sample\n\n## When to Use\n- sample trigger\n\n## Long Doctrine\n"
        + "evidence detail\n" * 80,
        encoding="utf-8",
    )

    packet = mod.build_split_packet(skill_path)

    assert packet["skill"] == "sample"
    assert packet["reference_path"] == "references/extracted-detail.md"
    assert "evidence detail" in packet["reference_markdown"]
    assert len(packet["router_markdown"].splitlines()) < len(skill_path.read_text(encoding="utf-8").splitlines())
    assert "references/extracted-detail.md" in packet["router_markdown"]


def test_wiki_knowledge_scout_finds_clusters_and_external_candidates(tmp_path):
    mod = _load_module("wiki_knowledge_scout", "scripts/wiki_knowledge_scout.py")
    brain = tmp_path / "2nd Brain"
    wiki = brain / "Wiki"
    sources = brain / "Sources" / "Completed"
    wiki.mkdir(parents=True)
    sources.mkdir(parents=True)
    (wiki / "northstar.md").write_text("# NorthStar\nshipit launch agent skill\n", encoding="utf-8")
    (wiki / "shipit.md").write_text("# ShipIt\nlaunch skill tests\n", encoding="utf-8")
    (sources / "anthropic-skills.md").write_text("# Anthropic Skills\nskill routing handoff launch shipit\n", encoding="utf-8")

    result = mod.scout(brain, limit=5)

    assert result["clusters"]
    top = result["clusters"][0]
    assert top["density"] > 0
    assert any("anthropic-skills.md" in c["path"] for c in result["external_candidates"])


def test_priority_path_router_selects_one_shipit_lane_and_defers_noise():
    mod = _load_module("priority_path_router", "scripts/priority_path_router.py")
    result = mod.route_priority(
        "Need production launch but tests unknown; also maybe redesign docs and investigate vendors"
    )

    assert result["lane"] == "launch-project-audit"
    assert result["status"] == "LOCAL_SAFE"
    assert "vendor" in " ".join(result["deferred_noise"]).lower()
    assert result["next_artifact"]
