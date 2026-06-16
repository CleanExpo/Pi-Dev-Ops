from __future__ import annotations

import argparse
from pathlib import Path

from scripts import capability_scout, run_capability_loop


def test_run_loop_writes_brain_and_validates_crm_payload(tmp_path, monkeypatch):
    discovery = capability_scout.Discovery(
        title="microsoft/agent-framework",
        url="https://github.com/microsoft/agent-framework",
        source_type="github",
        summary="Agent orchestration framework for Python workflows and MCP tools.",
        metadata={"stars": 2000},
    )
    monkeypatch.setattr(run_capability_loop.capability_scout, "fetch_live_discoveries", lambda _limit: [discovery])

    projects = tmp_path / "projects.json"
    args = argparse.Namespace(
        limit=3,
        min_score=45,
        brain_root=tmp_path / "brain",
        projects=projects,
        crm_url="http://localhost/api/command-center/control-panel/capability-intake",
        token_env="UNITE_CRM_ADMIN_TOKEN",
        post=False,
        json=True,
    )
    projects.write_text(
        '{"projects":[{"id":"pi-dev-ops","repo":"CleanExpo/Pi-Dev-Ops","stack":["Python"]}]}',
        encoding="utf-8",
    )

    result = run_capability_loop.run_loop(args)

    assert result["ok"] is True
    assert result["discoveries"] == 1
    assert result["candidates"] == 1
    assert result["crm_import"]["mode"] == "dry-run"
    assert result["crm_import"]["proposal_count"] == 1
    assert Path(result["brain"]["manifest_path"]).exists()
