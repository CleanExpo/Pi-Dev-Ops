"""Fail-closed I/O and stale-baseline red-team cases."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path


import pytest

from swarm.nexus.agent_registry import (
    RegistryValidationError,
    load_registry,
    normalised_projection_sha,
    render_catalogue,
    validate_catalogue,
    validate_projection_drift,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / ".harness/agents/registry.yaml"
MANIFEST = REPO_ROOT / "agentskills.json"
CONFIG = REPO_ROOT / ".harness/config.yaml"


@pytest.mark.parametrize(
    ("registry", "manifest", "config", "rule"),
    [
        (Path("missing-registry"), MANIFEST, CONFIG, "registry-readable"),
        (REGISTRY, Path("missing-manifest"), CONFIG, "skills-manifest-readable"),
        (REGISTRY, MANIFEST, Path("missing-config"), "model-policy-readable"),
    ],
)
def test_missing_sources_fail_with_specific_read_rule(
    registry: Path, manifest: Path, config: Path, rule: str
) -> None:
    with pytest.raises(RegistryValidationError, match=f"rule={rule}"):
        load_registry(registry, manifest, config)


def test_stale_projection_baseline_fails_closed() -> None:
    registry = load_registry(REGISTRY, MANIFEST, CONFIG)
    agents_path = REPO_ROOT / ".agents/skills/skybridge/SKILL.md"
    claude_path = REPO_ROOT / ".claude/skills/skybridge/SKILL.md"
    stale = {
        "id": "skybridge",
        "agents_sha256": normalised_projection_sha(agents_path),
        "claude_sha256": normalised_projection_sha(claude_path),
        "rationale": "Red-team stale baseline fixture.",
    }
    mutated = replace(
        registry,
        accepted_projection_drift=(*registry.accepted_projection_drift, stale),
    )

    with pytest.raises(RegistryValidationError, match="rule=stale-drift-baseline"):
        validate_projection_drift(REPO_ROOT, mutated)


def test_missing_catalogue_fails_with_read_rule(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY, MANIFEST, CONFIG)

    with pytest.raises(RegistryValidationError, match="rule=catalogue-readable"):
        validate_catalogue(tmp_path / "missing.md", render_catalogue(registry))


def _projection_pair(tmp_path: Path, agents: str, claude: str) -> Path:
    root = tmp_path / "repo"
    for vendor, content in ((".agents", agents), (".claude", claude)):
        path = root / vendor / "skills/shared/SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_malformed_projection_has_structured_read_error(tmp_path: Path) -> None:
    root = _projection_pair(
        tmp_path,
        "---\nname: [\n---\n# shared\n",
        "---\nname: shared\n---\n# shared\n",
    )

    with pytest.raises(RegistryValidationError, match="rule=projection-readable"):
        validate_projection_drift(
            root,
            replace(
                load_registry(REGISTRY, MANIFEST, CONFIG),
                accepted_projection_drift=(),
            ),
        )


def test_non_mapping_projection_frontmatter_has_structured_read_error(
    tmp_path: Path,
) -> None:
    root = _projection_pair(
        tmp_path,
        "---\n- not\n- a-mapping\n---\n# shared\n",
        "---\nname: shared\n---\n# shared\n",
    )

    with pytest.raises(RegistryValidationError, match="rule=projection-readable"):
        validate_projection_drift(
            root,
            replace(
                load_registry(REGISTRY, MANIFEST, CONFIG),
                accepted_projection_drift=(),
            ),
        )


def test_only_leading_command_heading_is_vendor_normalised(tmp_path: Path) -> None:
    root = _projection_pair(
        tmp_path,
        "---\nname: shared\n---\nIntro.\n# /shared\n",
        "---\nname: shared\n---\nIntro.\n# shared\n",
    )

    with pytest.raises(RegistryValidationError, match="rule=new-projection-drift"):
        validate_projection_drift(
            root,
            replace(
                load_registry(REGISTRY, MANIFEST, CONFIG),
                accepted_projection_drift=(),
            ),
        )
