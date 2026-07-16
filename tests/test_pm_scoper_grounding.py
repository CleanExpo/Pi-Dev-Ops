# tests/test_pm_scoper_grounding.py
from pathlib import Path


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


def test_build_research_prompt_falls_back_when_primary_missing(tmp_path, monkeypatch, caplog):
    """Anchor present but its primary file is gone → reground is non-FRESH, so the
    prompt drops the transcript block, uses description only, and logs the status."""
    import logging
    from app.server import grounding
    # Anchor points at a file that is never written under tmp_path → MISSING.
    anchor = grounding.record(
        primary_source="brain/plaud/gone.md",
        derived_from="brain/plaud/gone.md",
        parent_text="original transcript",
    )
    block = grounding.anchor_to_block(anchor)

    import swarm.pm_scoper as pm
    monkeypatch.setattr(pm, "_GROUND_REPO_ROOT", tmp_path)
    ticket = {
        "identifier": "RA-777",
        "title": "Do the thing",
        "description": "ambiguous description.\n\n" + block,
    }
    with caplog.at_level(logging.INFO):
        prompt = pm._build_research_prompt(ticket)
    # No transcript prepended — description-only fallback.
    assert "Original primary source" not in prompt
    assert "ambiguous description." in prompt
    assert "RA-777" in prompt
    assert any("ungrounded" in rec.message.lower() for rec in caplog.records)
