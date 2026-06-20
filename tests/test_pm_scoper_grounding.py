# tests/test_pm_scoper_grounding.py
from pathlib import Path
import importlib


def test_build_research_prompt_prepends_transcript(tmp_path, monkeypatch):
    from app.server import grounding
    plaud = tmp_path / "brain" / "plaud" / "itr.md"
    plaud.parent.mkdir(parents=True)
    plaud.write_text("FULL TRANSCRIPT: the ITR button referral system ...", encoding="utf-8")
    anchor = grounding.record(
        primary_source="brain/plaud/itr.md",
        derived_from="brain/plaud/itr.md",
        parent_text=plaud.read_text(),
    )
    block = grounding.anchor_to_block(anchor)

    import swarm.pm_scoper as pm
    monkeypatch.setattr(pm, "_GROUND_REPO_ROOT", tmp_path)
    ticket = {
        "identifier": "RA-512",
        "title": "Scan the flowchart",
        "description": "Scan the flowchart photo.\n\n" + block,
    }
    prompt = pm._build_research_prompt(ticket)
    assert "FULL TRANSCRIPT" in prompt
    assert "RA-512" in prompt


def test_build_research_prompt_falls_back_without_anchor(tmp_path, monkeypatch):
    import swarm.pm_scoper as pm
    monkeypatch.setattr(pm, "_GROUND_REPO_ROOT", tmp_path)
    ticket = {"identifier": "RA-1", "title": "T", "description": "no anchor here"}
    prompt = pm._build_research_prompt(ticket)
    assert "RA-1" in prompt
    assert "no anchor here" in prompt
