from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_senior_harness.sh"


def test_installer_aligns_three_skill_roots_to_one_control_stack(tmp_path: Path) -> None:
    environment = dict(os.environ, HOME=str(tmp_path))
    subprocess.run(["bash", str(INSTALLER)], check=True, env=environment, capture_output=True, text=True)

    for host in (".codex", ".claude", ".agents"):
        for skill in ("senior-harness", "model-router", "unlazy"):
            installed = tmp_path / host / "skills" / skill
            assert installed.is_symlink()
            assert installed.resolve() == (REPO_ROOT / "skills" / skill).resolve()


def test_installer_refuses_to_replace_a_real_skill_directory(tmp_path: Path) -> None:
    protected = tmp_path / ".agents" / "skills" / "senior-harness"
    protected.mkdir(parents=True)
    (protected / "SKILL.md").write_text("local control\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(INSTALLER)],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert "refusing to replace real path" in result.stderr
    assert (protected / "SKILL.md").read_text(encoding="utf-8") == "local control\n"
    assert not (tmp_path / ".codex" / "skills" / "senior-harness").exists()
    assert not (tmp_path / ".codex" / "skills" / "senior-harness").exists()
    assert not (tmp_path / ".claude" / "skills" / "senior-harness").exists()
