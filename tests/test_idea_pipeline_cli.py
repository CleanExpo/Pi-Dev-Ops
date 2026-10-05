"""UNI-2633 — CLI examine / dispose / GO."""

from __future__ import annotations

from pathlib import Path

from app.server.idea_pipeline import go_ticket
from scripts.idea_pipeline import main


def _fake_ticket(_packet, *, gql=None):
    """W1b: execute now files a Linear ticket; tests never reach Linear."""
    return {"id": "i1", "identifier": "RA-TEST", "url": "u", "state": "Ready for Pi-Dev"}


def test_cli_intake_dispose_go_execute(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(go_ticket, "file_go_ticket", _fake_ticket)
    idea = "Teach shop owners to grow with short self-paced video lessons."
    assert main(["--root", str(tmp_path), "intake", idea]) == 0
    created = capsys.readouterr().out
    assert "idea-" in created
    assert main(["--root", str(tmp_path), "snapshot"]) == 0
    snap = capsys.readouterr().out
    idea_id = [part for part in created.split('"') if part.startswith("idea-")][0]
    assert main(["--root", str(tmp_path), "dispose", idea_id, "PROMOTE"]) == 0
    assert main(["--root", str(tmp_path), "execute", idea_id]) == 2
    err = capsys.readouterr().err
    assert "without GO" in err
    assert main(["--root", str(tmp_path), "go", idea_id]) == 0
    assert main(["--root", str(tmp_path), "execute", idea_id]) == 0
    out = capsys.readouterr().out
    assert '"executed": false' in out
    assert snap
