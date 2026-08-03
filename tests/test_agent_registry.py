"""Governed Nexus agent registry validation."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
import yaml

from swarm.nexus.agent_registry import RegistryValidationError


ROLE_IDS = {
    "scout",
    "planner",
    "builder",
    "verifier",
    "reviewer",
    "security",
    "ci-recovery",
    "release-monitor",
}


def _agent(agent_id: str) -> dict[str, object]:
    return {
        "id": agent_id,
        "purpose": f"Shadow {agent_id} work with governed evidence.",
        "model_policy_role": "monitor",
        "risk_tier_ceiling": 0,
        "skills": ["architecture"],
        "evidence": ["test-result"],
        "status": "shadow",
    }


def _repo(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "repo"
    registry = root / ".harness" / "agents" / "registry.yaml"
    manifest = root / "agentskills.json"
    config = root / ".harness" / "config.yaml"
    catalogue = root / "docs" / "agents" / "README.md"
    registry.parent.mkdir(parents=True)
    catalogue.parent.mkdir(parents=True)
    (root / ".agents" / "skills" / "shared").mkdir(parents=True)
    (root / "skills" / "shared").mkdir(parents=True)
    projection = "---\nname: shared\ndescription: shared\n---\n# shared\n\nSame body.\n"
    (root / ".agents" / "skills" / "shared" / "SKILL.md").write_text(projection)
    (root / "skills" / "shared" / "SKILL.md").write_text(projection)
    registry.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "agents": [_agent(agent_id) for agent_id in sorted(ROLE_IDS)],
                "accepted_projection_drift": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps({"skills": [{"id": "architecture"}]}), encoding="utf-8"
    )
    config.write_text("agents:\n  monitor: {model: haiku}\n", encoding="utf-8")
    return {
        "root": root,
        "registry": registry,
        "manifest": manifest,
        "config": config,
        "catalogue": catalogue,
    }


def _load(paths: dict[str, Path]):
    module = importlib.import_module("swarm.nexus.agent_registry")
    return module.load_registry(
        paths["registry"], paths["manifest"], paths["config"]
    )


def _registry_data(paths: dict[str, Path]) -> dict[str, object]:
    return yaml.safe_load(paths["registry"].read_text(encoding="utf-8"))


def _write_registry(paths: dict[str, Path], data: object) -> None:
    paths["registry"].write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _replace_agent(
    data: dict[str, object], index: int, key: str, value: object
) -> dict[str, object]:
    agents = [dict(agent) for agent in data["agents"]]
    agents[index][key] = value
    return {**data, "agents": agents}


def test_loads_exact_shadow_role_set_from_known_policy_and_skills(tmp_path: Path) -> None:
    paths = _repo(tmp_path)

    loaded = _load(paths)

    assert {agent.id for agent in loaded.agents} == ROLE_IDS
    assert all(agent.status == "shadow" for agent in loaded.agents)


@pytest.mark.parametrize(
    ("mutation", "rule"),
    [
        (lambda data: [], "registry-shape"),
        (lambda data: {**data, "version": True}, "registry-version"),
        (lambda data: {**data, "version": 1.0}, "registry-version"),
        (lambda data: {**data, "agents": {}}, "agents-shape"),
        (lambda data: {**data, "agents": [*data["agents"][:-1], "bad"]}, "agent-shape"),
        (lambda data: _replace_agent(data, 0, "id", "../scout"), "agent-id"),
        (lambda data: _replace_agent(data, 0, "purpose", ""), "agent-purpose"),
        (lambda data: _replace_agent(data, 0, "model_policy_role", "invented"), "model-policy-role"),
        (lambda data: _replace_agent(data, 0, "model_policy_role", ["monitor"]), "model-policy-role"),
        (lambda data: _replace_agent(data, 0, "risk_tier_ceiling", True), "risk-tier"),
        (lambda data: _replace_agent(data, 0, "risk_tier_ceiling", 0.0), "risk-tier"),
        (lambda data: _replace_agent(data, 0, "risk_tier_ceiling", 4), "risk-tier"),
        (lambda data: _replace_agent(data, 0, "skills", []), "skills-shape"),
        (lambda data: _replace_agent(data, 0, "skills", ["missing-skill"]), "unknown-skill"),
        (lambda data: _replace_agent(data, 0, "evidence", []), "evidence"),
        (lambda data: _replace_agent(data, 0, "evidence", ["../unsafe"]), "evidence"),
        (lambda data: _replace_agent(data, 0, "status", "active"), "shadow-only"),
        (lambda data: _replace_agent(data, 1, "id", data["agents"][0]["id"]), "duplicate-agent-id"),
        (lambda data: {**data, "agents": data["agents"][:-1]}, "exact-role-set"),
        (lambda data: {**data, "accepted_projection_drift": {}}, "drift-baseline-shape"),
    ],
)
def test_registry_rules_fail_closed(tmp_path: Path, mutation, rule: str) -> None:
    paths = _repo(tmp_path)
    _write_registry(paths, mutation(_registry_data(paths)))

    with pytest.raises(RegistryValidationError, match=f"rule={rule}"):
        _load(paths)


@pytest.mark.parametrize(
    ("target", "content", "rule"),
    [
        ("manifest", "[]", "skills-manifest-shape"),
        ("manifest", '{"skills":[42]}', "skills-manifest-shape"),
        ("config", "[]\n", "model-policy-shape"),
        ("config", "agents:\n  monitor: nope\n", "model-policy-shape"),
    ],
)
def test_dependency_sources_reject_unsafe_shapes(
    tmp_path: Path, target: str, content: str, rule: str
) -> None:
    paths = _repo(tmp_path)
    paths[target].write_text(content, encoding="utf-8")

    with pytest.raises(RegistryValidationError, match=f"rule={rule}"):
        _load(paths)


@pytest.mark.parametrize(
    ("mutation", "rule"),
    [
        (lambda data: {**data, "unexpected": True}, "registry-fields"),
        (lambda data: _replace_agent(data, 0, "unexpected", True), "agent-fields"),
        (lambda data: _replace_agent(data, 0, "skills", ["architecture"] * 2), "duplicate-skill"),
        (lambda data: _replace_agent(data, 0, "evidence", ["test-result"] * 2), "duplicate-evidence"),
        (lambda data: {**data, "accepted_projection_drift": ["bad"]}, "drift-baseline-entry"),
        (
            lambda data: {
                **data,
                "accepted_projection_drift": [
                    {
                        "id": "shared",
                        "agents_sha256": "bad",
                        "canonical_sha256": "0" * 64,
                        "rationale": "Known vendor projection difference.",
                    }
                ],
            },
            "drift-baseline-entry",
        ),
    ],
)
def test_additional_unsafe_shapes_fail_closed(tmp_path: Path, mutation, rule: str) -> None:
    paths = _repo(tmp_path)
    _write_registry(paths, mutation(_registry_data(paths)))

    with pytest.raises(RegistryValidationError, match=f"rule={rule}"):
        _load(paths)


def test_duplicate_skill_ids_in_manifest_fail_closed(tmp_path: Path) -> None:
    paths = _repo(tmp_path)
    paths["manifest"].write_text(
        json.dumps({"skills": [{"id": "architecture"}, {"id": "architecture"}]}),
        encoding="utf-8",
    )

    with pytest.raises(RegistryValidationError, match="rule=duplicate-manifest-skill"):
        _load(paths)


def test_projection_normalisation_ignores_vendor_frontmatter_and_command_heading(
    tmp_path: Path,
) -> None:
    paths = _repo(tmp_path)
    agents_projection = (
        "---\nname: shared\ndescription: shared\nargument-hint: x\n"
        "allowed-tools: Read\ndisable-model-invocation: true\n---\n"
        "# /shared\n\nSame body.\n"
    )
    (paths["root"] / ".agents/skills/shared/SKILL.md").write_text(
        agents_projection, encoding="utf-8"
    )
    module = importlib.import_module("swarm.nexus.agent_registry")

    assert module.validate_projection_drift(paths["root"], _load(paths)) == 0


def test_new_projection_drift_fails_without_baseline(tmp_path: Path) -> None:
    paths = _repo(tmp_path)
    projection = paths["root"] / ".agents/skills/shared/SKILL.md"
    projection.write_text(projection.read_text() + "New drift.\n", encoding="utf-8")
    module = importlib.import_module("swarm.nexus.agent_registry")

    with pytest.raises(RegistryValidationError, match="rule=new-projection-drift"):
        module.validate_projection_drift(paths["root"], _load(paths))


def test_exact_projection_drift_baseline_is_accepted_and_change_fails(
    tmp_path: Path,
) -> None:
    paths = _repo(tmp_path)
    projection = paths["root"] / ".agents/skills/shared/SKILL.md"
    projection.write_text(projection.read_text() + "Accepted drift.\n", encoding="utf-8")
    module = importlib.import_module("swarm.nexus.agent_registry")
    data = _registry_data(paths)
    data["accepted_projection_drift"] = [
        {
            "id": "shared",
            "agents_sha256": module.normalised_projection_sha(
                paths["root"] / ".agents/skills/shared/SKILL.md"
            ),
            "canonical_sha256": module.normalised_projection_sha(
                paths["root"] / "skills/shared/SKILL.md"
            ),
            "rationale": "Existing accepted vendor divergence; detection only.",
        }
    ]
    _write_registry(paths, data)
    loaded = _load(paths)

    assert module.validate_projection_drift(paths["root"], loaded) == 1
    projection.write_text(projection.read_text() + "Unbaselined change.\n")
    with pytest.raises(RegistryValidationError, match="rule=changed-projection-drift"):
        module.validate_projection_drift(paths["root"], loaded)


def test_projection_without_canonical_source_fails(tmp_path: Path) -> None:
    paths = _repo(tmp_path)
    (paths["root"] / "skills/shared/SKILL.md").unlink()
    module = importlib.import_module("swarm.nexus.agent_registry")

    with pytest.raises(RegistryValidationError, match="rule=canonical-source-missing"):
        module.validate_projection_drift(paths["root"], _load(paths))


def test_catalogue_render_is_deterministic_and_has_generated_header(
    tmp_path: Path,
) -> None:
    paths = _repo(tmp_path)
    module = importlib.import_module("swarm.nexus.agent_registry")
    loaded = _load(paths)

    first = module.render_catalogue(loaded)
    second = module.render_catalogue(loaded)

    assert first == second
    assert first.startswith("<!-- GENERATED FILE — DO NOT EDIT")
    assert first.count("## `") == 8


def test_catalogue_check_requires_byte_identical_content(tmp_path: Path) -> None:
    paths = _repo(tmp_path)
    module = importlib.import_module("swarm.nexus.agent_registry")
    expected = module.render_catalogue(_load(paths))
    paths["catalogue"].write_text(expected, encoding="utf-8")

    module.validate_catalogue(paths["catalogue"], expected)
    paths["catalogue"].write_text(expected + "drift", encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="rule=catalogue-drift"):
        module.validate_catalogue(paths["catalogue"], expected)
