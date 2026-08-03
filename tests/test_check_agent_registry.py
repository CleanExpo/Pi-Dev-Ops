"""CLI and real-repository gates for the Nexus agent registry."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from app.server import config_loader


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_agent_registry.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _copy_registry_surface(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "agents").mkdir(parents=True)
    (root / "config" / "harness" / "agents").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "agentskills.json", root / "agentskills.json")
    shutil.copy2(config_loader.CONFIG_YAML, root / "config/harness/config.yaml")
    shutil.copy2(
        config_loader.CONFIG_DIR / "agents/registry.yaml",
        root / "config/harness/agents/registry.yaml",
    )
    shutil.copytree(REPO_ROOT / ".agents/skills", root / ".agents/skills")
    shutil.copytree(REPO_ROOT / "skills", root / "skills")
    return root


def test_cli_writes_byte_stable_catalogue_and_then_passes(tmp_path: Path) -> None:
    root = _copy_registry_surface(tmp_path)

    first = _run(root, "--write-catalogue")
    catalogue = root / "docs/agents/README.md"
    first_bytes = catalogue.read_bytes()
    second = _run(root, "--write-catalogue")

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert catalogue.read_bytes() == first_bytes
    assert _run(root).returncode == 0


def test_cli_refuses_symlinked_catalogue_without_touching_external_target(
    tmp_path: Path,
) -> None:
    root = _copy_registry_surface(tmp_path)
    catalogue = root / "docs/agents/README.md"
    external = tmp_path / "external-catalogue.md"
    external.write_text("sentinel", encoding="utf-8")
    catalogue.symlink_to(external)

    result = _run(root, "--write-catalogue")

    assert result.returncode == 1
    assert "rule=catalogue-write-path" in result.stderr
    assert external.read_text(encoding="utf-8") == "sentinel"


def test_cli_reports_file_id_rule_and_reproduction_on_failure(tmp_path: Path) -> None:
    root = _copy_registry_surface(tmp_path)
    registry_path = root / "config/harness/agents/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["agents"][0]["id"] = "../escape"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    result = _run(root)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "file=" in output
    assert "id=../escape" in output
    assert "rule=agent-id" in output
    assert "reproduce:" in output


def test_real_repository_registry_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "8 shadow agents" in result.stdout
    assert "4 accepted projection divergences" in result.stdout


def test_registry_gate_is_additive_to_ci_and_handoff_generated_checks() -> None:
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    handoff = (REPO_ROOT / "scripts/handoff-loop.sh").read_text(encoding="utf-8")

    assert ci.count("check_provisioning.py") == 1
    assert ci.count("check_agent_registry.py") == 1
    assert ci.index("check_provisioning.py") < ci.index("check_agent_registry.py")
    assert 'gate "generated-agent-registry"' in handoff
    assert "check_agent_registry.py" in handoff
