"""Read-only loader and validator for the shadow Nexus agent registry."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .autonomy_ladder import (
    TIER_IRREVERSIBLE,
    TIER_LOCAL,
    TIER_OUTWARD,
    TIER_READ,
)
from .projection_drift import normalised_projection_sha as normalised_projection_sha
from .projection_drift import validate_projection_drift as _validate_projection_drift
from .agent_catalogue import render_catalogue as render_catalogue
from .agent_catalogue import validate_catalogue as _validate_catalogue

ROLE_IDS = frozenset(
    {"scout", "planner", "builder", "verifier", "reviewer", "security",
     "ci-recovery", "release-monitor"}
)
VALID_TIERS = frozenset(
    {TIER_READ, TIER_LOCAL, TIER_OUTWARD, TIER_IRREVERSIBLE}
)
_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_FIELDS = {"version", "agents", "accepted_projection_drift"}
_AGENT_FIELDS = {
    "id",
    "purpose",
    "model_policy_role",
    "risk_tier_ceiling",
    "skills",
    "evidence",
    "status",
}
_DRIFT_FIELDS = {"id", "agents_sha256", "claude_sha256", "rationale"}


class RegistryValidationError(ValueError):
    """A fail-closed registry validation error with a stable rule identifier."""

    def __init__(self, file: Path, rule: str, detail: str, agent_id: str = "-"):
        self.file = file
        self.rule = rule
        self.detail = detail
        self.agent_id = agent_id
        super().__init__(f"file={file} id={agent_id} rule={rule} detail={detail}")


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    purpose: str
    model_policy_role: str
    risk_tier_ceiling: int
    skills: tuple[str, ...]
    evidence: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class AgentRegistry:
    version: int
    agents: tuple[AgentDefinition, ...]
    accepted_projection_drift: tuple[dict[str, str], ...]


def _read_yaml(path: Path, rule: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RegistryValidationError(path, rule, str(exc)) from exc


def _read_json(path: Path, rule: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryValidationError(path, rule, str(exc)) from exc


def _known_skill_ids(path: Path) -> set[str]:
    data = _read_json(path, "skills-manifest-readable")
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise RegistryValidationError(
            path, "skills-manifest-shape", "expected object.skills list"
        )
    ids: set[str] = set()
    for index, item in enumerate(data["skills"]):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RegistryValidationError(
                path,
                "skills-manifest-shape",
                f"skills[{index}].id must be a string",
            )
        skill_id = item["id"]
        if skill_id in ids:
            raise RegistryValidationError(
                path, "duplicate-manifest-skill", f"duplicate skill id {skill_id!r}"
            )
        ids.add(skill_id)
    return ids


def _model_policy_roles(path: Path) -> set[str]:
    data = _read_yaml(path, "model-policy-readable")
    if not isinstance(data, dict) or not isinstance(data.get("agents"), dict):
        raise RegistryValidationError(
            path, "model-policy-shape", "expected object.agents mapping"
        )
    if not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in data["agents"].items()
    ):
        raise RegistryValidationError(
            path, "model-policy-shape", "agents must map string roles to objects"
        )
    return set(data["agents"])


def _agent_from_raw(
    raw: Any,
    index: int,
    path: Path,
    known_skills: set[str],
    model_roles: set[str],
) -> AgentDefinition:
    if not isinstance(raw, dict):
        raise RegistryValidationError(
            path, "agent-shape", f"agents[{index}] must be a mapping"
        )
    agent_id = str(raw.get("id", "-"))
    if set(raw) != _AGENT_FIELDS:
        raise RegistryValidationError(
            path, "agent-fields", "agent fields are missing or unknown", agent_id
        )
    if not _ID_RE.fullmatch(agent_id):
        raise RegistryValidationError(
            path, "agent-id", "must match lowercase kebab-case", agent_id
        )
    purpose = raw["purpose"]
    if not isinstance(purpose, str) or not purpose.strip():
        raise RegistryValidationError(
            path, "agent-purpose", "purpose must be a non-empty string", agent_id
        )
    model_role = raw["model_policy_role"]
    if model_role not in model_roles:
        raise RegistryValidationError(
            path, "model-policy-role", f"unknown role {model_role!r}", agent_id
        )
    tier = raw["risk_tier_ceiling"]
    if isinstance(tier, bool) or tier not in VALID_TIERS:
        raise RegistryValidationError(
            path, "risk-tier", "must be an integer autonomy tier 0..3", agent_id
        )
    skills = raw["skills"]
    if (
        not isinstance(skills, list)
        or not skills
        or not all(isinstance(item, str) for item in skills)
    ):
        raise RegistryValidationError(
            path, "skills-shape", "skills must be a non-empty string list", agent_id
        )
    if len(skills) != len(set(skills)):
        raise RegistryValidationError(
            path, "duplicate-skill", "skills must be unique", agent_id
        )
    unknown = sorted(set(skills) - known_skills)
    if unknown:
        raise RegistryValidationError(
            path, "unknown-skill", f"unknown skills: {', '.join(unknown)}", agent_id
        )
    evidence = raw["evidence"]
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(
            isinstance(item, str) and _ID_RE.fullmatch(item) for item in evidence
        )
    ):
        raise RegistryValidationError(
            path, "evidence", "evidence must be non-empty kebab-case strings", agent_id
        )
    if len(evidence) != len(set(evidence)):
        raise RegistryValidationError(
            path, "duplicate-evidence", "evidence kinds must be unique", agent_id
        )
    status = raw["status"]
    if status != "shadow":
        raise RegistryValidationError(
            path, "shadow-only", "status must be shadow", agent_id
        )
    return AgentDefinition(
        agent_id,
        purpose.strip(),
        model_role,
        tier,
        tuple(skills),
        tuple(evidence),
        status,
    )


def _validate_drift_baseline(path: Path, drift: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(drift, list):
        raise RegistryValidationError(
            path, "drift-baseline-shape", "accepted_projection_drift must be a list"
        )
    ids: set[str] = set()
    for entry in drift:
        valid = (
            isinstance(entry, dict)
            and set(entry) == _DRIFT_FIELDS
            and isinstance(entry.get("id"), str)
            and bool(_ID_RE.fullmatch(entry["id"]))
            and isinstance(entry.get("agents_sha256"), str)
            and bool(_SHA_RE.fullmatch(entry["agents_sha256"]))
            and isinstance(entry.get("claude_sha256"), str)
            and bool(_SHA_RE.fullmatch(entry["claude_sha256"]))
            and isinstance(entry.get("rationale"), str)
            and bool(entry["rationale"].strip())
            and entry["id"] not in ids
        )
        if not valid:
            raise RegistryValidationError(
                path,
                "drift-baseline-entry",
                "baseline requires unique id, two SHA-256 hashes, and rationale",
            )
        ids.add(entry["id"])
    return tuple(drift)


def load_registry(
    registry_path: Path,
    skills_manifest_path: Path,
    model_policy_path: Path,
) -> AgentRegistry:
    """Load and validate the registry without mutating any source or projection."""
    data = _read_yaml(registry_path, "registry-readable")
    if not isinstance(data, dict):
        raise RegistryValidationError(registry_path, "registry-shape", "expected mapping")
    if set(data) != _REGISTRY_FIELDS:
        raise RegistryValidationError(
            registry_path, "registry-fields", "registry fields are missing or unknown"
        )
    if data["version"] != 1 or isinstance(data["version"], bool):
        raise RegistryValidationError(
            registry_path, "registry-version", "version must be integer 1"
        )
    raw_agents = data["agents"]
    if not isinstance(raw_agents, list):
        raise RegistryValidationError(
            registry_path, "agents-shape", "agents must be a list"
        )
    known_skills = _known_skill_ids(skills_manifest_path)
    model_roles = _model_policy_roles(model_policy_path)
    agents = tuple(
        _agent_from_raw(raw, index, registry_path, known_skills, model_roles)
        for index, raw in enumerate(raw_agents)
    )
    ids = [agent.id for agent in agents]
    if len(ids) != len(set(ids)):
        raise RegistryValidationError(
            registry_path, "duplicate-agent-id", "agent ids must be unique"
        )
    if set(ids) != ROLE_IDS:
        raise RegistryValidationError(
            registry_path, "exact-role-set", f"expected: {', '.join(sorted(ROLE_IDS))}"
        )
    drift = _validate_drift_baseline(
        registry_path, data["accepted_projection_drift"]
    )
    return AgentRegistry(1, agents, drift)


def validate_projection_drift(repo_root: Path, registry: AgentRegistry) -> int:
    """Validate cross-tool projections against the detection-only baseline."""
    return _validate_projection_drift(repo_root, registry, RegistryValidationError)


def validate_catalogue(path: Path, expected: str) -> None:
    """Require byte-identical regeneration of the checked-in catalogue."""
    _validate_catalogue(path, expected, RegistryValidationError)
