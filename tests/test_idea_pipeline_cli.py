"""UNI-2633 — CLI examine / dispose / GO."""

from __future__ import annotations

from pathlib import Path

from scripts.idea_pipeline import main


def test_cli_intake_dispose_go_execute(tmp_path: Path, capsys) -> None:
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
