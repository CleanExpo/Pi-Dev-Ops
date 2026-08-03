"""Detection-only comparison of Codex projections against canonical repo skills."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

import yaml

_VENDOR_FRONTMATTER = frozenset(
    {"argument-hint", "allowed-tools", "disable-model-invocation"}
)
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_HEADING_RE = re.compile(r"\A(#\s+)/(?=[a-z0-9-]+\b)")


class _RegistryErrorFactory(Protocol):
    def __call__(
        self, file: Path, rule: str, detail: str, agent_id: str = "-"
    ) -> ValueError: ...


def _normalise_projection(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return _HEADING_RE.sub(r"\1", content, count=1)
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        raise ValueError("projection frontmatter must be a mapping")
    for key in _VENDOR_FRONTMATTER:
        frontmatter.pop(key, None)
    canonical_frontmatter = yaml.safe_dump(
        frontmatter, sort_keys=True, allow_unicode=True
    ).strip()
    body = _HEADING_RE.sub(r"\1", match.group(2), count=1)
    return f"---\n{canonical_frontmatter}\n---\n{body}"


def normalised_projection_sha(path: Path) -> str:
    """Hash projection content after documented vendor-only normalisation."""
    return hashlib.sha256(_normalise_projection(path).encode("utf-8")).hexdigest()


def _validated_projection_sha(path: Path, error_factory: _RegistryErrorFactory) -> str:
    try:
        return normalised_projection_sha(path)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        raise error_factory(path, "projection-readable", str(exc)) from exc


def validate_projection_drift(
    repo_root: Path, registry: object, error_factory: _RegistryErrorFactory
) -> int:
    """Fail on missing/new/changed drift without writing source or projections."""
    canonical_root = repo_root / "skills"
    agents_root = repo_root / ".agents" / "skills"
    agents = {path.parent.name: path for path in agents_root.glob("*/SKILL.md")}
    canonical = {
        skill_id: canonical_root / skill_id / "SKILL.md" for skill_id in agents
    }
    missing = sorted(
        skill_id for skill_id, path in canonical.items() if not path.is_file()
    )
    if missing:
        raise error_factory(
            repo_root,
            "canonical-source-missing",
            f"Codex projection has no canonical skills/<name>/SKILL.md source: {', '.join(missing)}",
        )

    raw_baseline = getattr(registry, "accepted_projection_drift")
    baseline = {entry["id"]: entry for entry in raw_baseline}
    accepted = 0
    for skill_id in sorted(agents):
        agents_sha = _validated_projection_sha(agents[skill_id], error_factory)
        canonical_sha = _validated_projection_sha(canonical[skill_id], error_factory)
        entry = baseline.get(skill_id)
        if agents_sha == canonical_sha:
            if entry:
                raise error_factory(
                    repo_root,
                    "stale-drift-baseline",
                    "projections now match; remove obsolete baseline",
                    skill_id,
                )
            continue
        if not entry:
            raise error_factory(
                repo_root,
                "new-projection-drift",
                "normalised vendor projections differ without an accepted baseline",
                skill_id,
            )
        if (entry["agents_sha256"], entry["canonical_sha256"]) != (
            agents_sha,
            canonical_sha,
        ):
            raise error_factory(
                repo_root,
                "changed-projection-drift",
                "normalised projection hash changed from accepted baseline",
                skill_id,
            )
        accepted += 1

    unknown = sorted(set(baseline) - set(agents))
    if unknown:
        raise error_factory(
            repo_root,
            "stale-drift-baseline",
            f"baseline ids are not projected: {', '.join(unknown)}",
        )
    return accepted
