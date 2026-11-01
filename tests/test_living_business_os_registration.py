"""Registration of the living-business-os skill (RA-8145 M1).

Checks wiring only: the skill is discovered, the agent registry still validates with it
attached to the verifier, and the generated manifests and catalogue are current. No Node,
and no rule logic: the rules are tested inside packages/living-business-os.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from src.tao import skills as tao_skills

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = "living-business-os"
SKILL_FILE = REPO_ROOT / "skills" / SKILL / "SKILL.md"
REGISTRY = REPO_ROOT / "config" / "harness" / "agents" / "registry.yaml"

# Role ids and risk ceilings must not move because a skill was attached to a role.
EXPECTED_CEILINGS = {
    "scout": 0,
    "planner": 0,
    "builder": 1,
    "verifier": 0,
    "reviewer": 0,
    "security": 0,
    "ci-recovery": 1,
    "release-monitor": 0,
}


def _agents() -> dict[str, dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return {a["id"]: a for a in data["agents"]}


def test_skill_is_discovered_from_this_repos_skills_root() -> None:
    found = tao_skills._scan(str(REPO_ROOT / "skills"))
    assert SKILL in found
    assert found[SKILL]["description"].strip()
    assert Path(found[SKILL]["path"]).resolve() == SKILL_FILE.resolve()


def test_skill_name_does_not_clash_with_the_library_copy() -> None:
    library = REPO_ROOT / "skills-library" / "skills" / SKILL
    assert not library.exists(), "a same-named skill in skills-library would be shadowed by skills/"


def test_verifier_has_the_skill_and_role_contract_is_unchanged() -> None:
    agents = _agents()
    assert agents["verifier"]["skills"] == ["verify-test", SKILL]
    for role, ceiling in EXPECTED_CEILINGS.items():
        assert agents[role]["risk_tier_ceiling"] == ceiling, role
    assert set(EXPECTED_CEILINGS) <= set(agents)
    # No other role picks the skill up.
    assert [r for r, a in agents.items() if SKILL in a.get("skills", [])] == ["verifier"]


def test_registry_validates_and_catalogue_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_agent_registry.py")],
        text=True,
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_manifest_lists_the_skill_with_the_current_file_hash() -> None:
    manifest = json.loads((REPO_ROOT / "agentskills.json").read_text(encoding="utf-8"))
    entries = [s for s in manifest["skills"] if s["id"] == SKILL]
    assert len(entries) == 1
    assert entries[0]["path"] == f"skills/{SKILL}/SKILL.md"
    assert entries[0]["sha256"] == hashlib.sha256(SKILL_FILE.read_bytes()).hexdigest()
    yaml_manifest = yaml.safe_load((REPO_ROOT / "agentskills.yaml").read_text(encoding="utf-8"))
    assert [s for s in yaml_manifest["skills"] if s["id"] == SKILL][0]["sha256"] == entries[0]["sha256"]


def test_skill_names_the_package_and_forbids_real_data() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert "packages/living-business-os" in text
    assert "Real customer or tenant data" in text
    assert "MANIFEST" in text
