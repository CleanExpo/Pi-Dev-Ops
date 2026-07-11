from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import skill_sync  # noqa: E402


def _skill(folder: Path, name: str, body: str = "Body\n", description: str | None = None) -> Path:
    skill_dir = folder / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    desc = description or f"Use when testing {name}."
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\n{body}",
        encoding="utf-8",
    )
    return skill_dir


def _repo(path: Path) -> None:
    (path / ".git").mkdir(parents=True)


def _ref(project_id: str, repo: str, path: Path) -> skill_sync.RepositoryRef:
    return skill_sync.RepositoryRef(project_id=project_id, repo=repo, path=path, status="scanned")


def test_unique_project_skill_detection(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    project = tmp_path / "Project"
    _skill(repo_root / "skills", "canonical")
    source = _skill(project / ".claude" / "skills", "fresh-skill")

    record = skill_sync.scan_skill(
        _ref("project", "CleanExpo/Project", project),
        source / "SKILL.md",
        repo_root,
        {"canonical": skill_sync.folder_hash(repo_root / "skills" / "canonical")},
    )

    assert record.classification == "PROJECT_UNIQUE"
    assert record.canonical_match is None


def test_identical_skill_deduplication(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    project = tmp_path / "Project"
    canonical = _skill(repo_root / "skills", "shared-skill", body="Same body\n")
    source = project / ".claude" / "skills" / "shared-skill"
    shutil.copytree(canonical, source)

    record = skill_sync.scan_skill(
        _ref("project", "CleanExpo/Project", project),
        source / "SKILL.md",
        repo_root,
        {"shared-skill": skill_sync.folder_hash(canonical)},
    )

    assert record.classification == "CANONICAL_IDENTICAL"
    assert record.canonical_match == "skills/shared-skill"


def test_name_conflict_detection(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    project = tmp_path / "Project"
    canonical = _skill(repo_root / "skills", "same-name", body="Canonical body\n")
    source = _skill(project / ".agents" / "skills", "same-name", body="Different body\n")

    record = skill_sync.scan_skill(
        _ref("project", "CleanExpo/Project", project),
        source / "SKILL.md",
        repo_root,
        {"same-name": skill_sync.folder_hash(canonical)},
    )

    assert record.classification == "NAME_CONFLICT"


def test_missing_reference_detection(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    project = tmp_path / "Project"
    source = _skill(project / "skills", "broken-ref", body="Read [missing](references/missing.md).\n")

    record = skill_sync.scan_skill(
        _ref("project", "CleanExpo/Project", project),
        source / "SKILL.md",
        repo_root,
        {},
    )

    assert record.classification == "INVALID"
    assert record.missing_references == ["references/missing.md"]


def test_apply_never_overwrites_existing_canonical_without_resolution(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    _skill(repo_root / "skills", "course-skill", body="Canonical body\n")
    source = _skill(tmp_path / "Source", "course-skill", body="New body\n")
    report = tmp_path / "report.md"
    report.write_text(
        f"- [x] APPROVE_PROMOTE name=course-skill source={source} "
        f"folder_sha256={skill_sync.folder_hash(source)}\n",
        encoding="utf-8",
    )

    manifest_path = skill_sync.apply_report(report, repo_root=repo_root, apply_dir=tmp_path / "applies")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["conflicted"][0]["name"] == "course-skill"
    assert (repo_root / "skills" / "course-skill" / "SKILL.md").read_text(encoding="utf-8").endswith("Canonical body\n")


def test_approved_only_promotion(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    approved = _skill(tmp_path / "Approved", "approved-skill")
    unapproved = _skill(tmp_path / "Unapproved", "unapproved-skill")
    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                f"- [x] APPROVE_PROMOTE name=approved-skill source={approved} folder_sha256={skill_sync.folder_hash(approved)}",
                f"- [ ] APPROVE_PROMOTE name=unapproved-skill source={unapproved} folder_sha256={skill_sync.folder_hash(unapproved)}",
            ]
        ),
        encoding="utf-8",
    )

    skill_sync.apply_report(report, repo_root=repo_root, apply_dir=tmp_path / "applies")

    assert (repo_root / "skills" / "approved-skill" / "SKILL.md").exists()
    assert not (repo_root / "skills" / "unapproved-skill").exists()


def test_manifest_regeneration_runs_when_module_exists(tmp_path: Path) -> None:
    repo_root = tmp_path / "Pi-Dev-Ops"
    (repo_root / "swarm").mkdir(parents=True)
    (repo_root / "swarm" / "__init__.py").write_text("", encoding="utf-8")
    (repo_root / "swarm" / "agentskills_manifest.py").write_text(
        "from pathlib import Path\nPath('agentskills.json').write_text('{\"ok\": true}\\n')\nprint('manifest ok')\n",
        encoding="utf-8",
    )
    source = _skill(tmp_path / "Source", "manifest-skill")
    report = tmp_path / "report.md"
    report.write_text(
        f"- [x] APPROVE_PROMOTE name=manifest-skill source={source} folder_sha256={skill_sync.folder_hash(source)}\n",
        encoding="utf-8",
    )

    manifest_path = skill_sync.apply_report(report, repo_root=repo_root, apply_dir=tmp_path / "applies")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["manifest_regeneration"]["status"] == "ok"
    assert (repo_root / "agentskills.json").exists()


def test_powershell_dry_run_output_contract() -> None:
    script = (REPO_ROOT / "scripts" / "install-skills.ps1").read_text(encoding="utf-8")
    assert "[switch]$DryRun" in script
    assert "LINK    $name" in script
    assert "(dry-run) " in script
    assert "linked" in script and "updated" in script and "current" in script
    assert "skipped" in script and "failed" in script


def test_powershell_dry_run_executes_when_pwsh_is_available(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        pytest.skip("PowerShell executable is not installed on this machine")
    target = tmp_path / "global-skills"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(REPO_ROOT / "scripts" / "install-skills.ps1"), "-DryRun", "-Target", str(target)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "(dry-run) done:" in result.stdout


def test_carsi_skill_appears_in_generated_manifest() -> None:
    manifest_path = REPO_ROOT / "agentskills.json"
    if not manifest_path.exists():
        pytest.skip("agentskills.json has not been regenerated in this checkout")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(skill["id"] == "carsi-course-production" for skill in manifest.get("skills", []))
