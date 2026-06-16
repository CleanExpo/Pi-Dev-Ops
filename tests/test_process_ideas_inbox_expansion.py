from __future__ import annotations

import json
from pathlib import Path

from scripts import process_ideas_inbox


def test_process_file_expands_idea_before_linear(tmp_path: Path, monkeypatch):
    inbox = tmp_path / "ideas.jsonl"
    inbox.write_text(
        json.dumps({
            "text": "System should expand raw ideas into adjacent research before building.",
            "user_name": "Phill",
            "ts": "2026-06-16T10:00:00+10:00",
        }) + "\n",
        encoding="utf-8",
    )
    created_issue: dict[str, str] = {}

    def fake_create_issue(api_key: str, title: str, description: str) -> str:
        created_issue["api_key"] = api_key
        created_issue["title"] = title
        created_issue["description"] = description
        return "RA-4242"

    monkeypatch.setattr(process_ideas_inbox, "linear_create_issue", fake_create_issue)

    already_done, created, failed = process_ideas_inbox.process_file(
        inbox,
        "lin_test",
        dry_run=False,
        brain_root=tmp_path / "2nd-brain",
    )

    assert (already_done, created, failed) == (0, 1, 0)
    assert created_issue["api_key"] == "lin_test"
    assert "Strategic Expansion" in created_issue["description"]
    assert "Adjacent opportunities" in created_issue["description"]
    assert "Research lanes" in created_issue["description"]
    assert "2nd-brain packet" in created_issue["description"]

    processed = json.loads(inbox.read_text(encoding="utf-8").strip())
    expansion = processed["idea_expansion"]
    assert processed["processed"] is True
    assert processed["linear_identifier"] == "RA-4242"
    assert expansion["crm_task_count"] == 3
    assert Path(expansion["decision_path"]).exists()
    assert Path(expansion["manifest_path"]).exists()
    assert Path(expansion["crm_bridge_path"]).exists()


def test_process_file_can_disable_expansion(tmp_path: Path, monkeypatch):
    inbox = tmp_path / "ideas.jsonl"
    inbox.write_text(
        json.dumps({"text": "Literal inbox idea", "user_name": "Phill"}) + "\n",
        encoding="utf-8",
    )
    descriptions: list[str] = []

    def fake_create_issue(api_key: str, title: str, description: str) -> str:
        descriptions.append(description)
        return "RA-4243"

    monkeypatch.setattr(process_ideas_inbox, "linear_create_issue", fake_create_issue)

    already_done, created, failed = process_ideas_inbox.process_file(
        inbox,
        "lin_test",
        dry_run=False,
        brain_root=tmp_path / "2nd-brain",
        expand=False,
    )

    assert (already_done, created, failed) == (0, 1, 0)
    assert "Strategic Expansion" not in descriptions[0]
