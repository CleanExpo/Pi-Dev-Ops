"""Review round 11 P1-EXECUTABLE-MODES-LOST: the copy wrote every file 0644, so a library script a
skill tells an agent to run directly failed with Permission denied."""
import os
import subprocess

from tests.test_skills_library_sync import _check, _resync, held_back, layout, library  # noqa: F401


def test_sync_keeps_the_executable_bit_and_check_notices_a_change(layout):  # noqa: F811
    script = layout["library"] / "skills" / "alpha" / "scripts" / "run.py"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env python3\nprint('ok')\n")
    script.chmod(0o755)
    _resync(layout)
    copied, skill_md = layout["dest"] / "alpha" / "scripts" / "run.py", layout["dest"] / "alpha" / "SKILL.md"
    assert subprocess.run([str(copied)], capture_output=True, text=True).stdout == "ok\n"
    assert not os.access(skill_md, os.X_OK)
    assert _check(layout) == []
    copied.chmod(0o644)
    assert any("executable" in p for p in _check(layout)), "a script lost its executable bit"
    copied.chmod(0o755)
    skill_md.chmod(0o755)
    assert any("executable" in p for p in _check(layout)), "a file gained an executable bit"
