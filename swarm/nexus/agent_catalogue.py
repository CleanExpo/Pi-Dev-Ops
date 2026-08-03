"""Deterministic human catalogue for the governed shadow agent registry."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence


class _Agent(Protocol):
    id: str
    purpose: str
    model_policy_role: str
    risk_tier_ceiling: int
    skills: tuple[str, ...]
    evidence: tuple[str, ...]
    status: str


class _Registry(Protocol):
    @property
    def agents(self) -> Sequence[_Agent]: ...


def render_catalogue(registry: _Registry) -> str:
    """Return byte-stable Markdown derived only from validated registry data."""
    lines = [
        "<!-- GENERATED FILE — DO NOT EDIT. Run: python scripts/check_agent_registry.py --write-catalogue -->",
        "",
        "# Nexus Shadow Agent Catalogue",
        "",
        "This catalogue is generated from `fence/agents/registry.yaml`.",
        "All roles are detection-only shadow definitions; this does not change runtime routing.",
        "",
    ]
    for agent in sorted(registry.agents, key=lambda item: item.id):
        lines.extend(
            [
                f"## `{agent.id}`",
                "",
                agent.purpose,
                "",
                f"- Status: `{agent.status}`",
                f"- Model policy role: `{agent.model_policy_role}`",
                f"- Risk tier ceiling: `L{agent.risk_tier_ceiling}`",
                f"- Skills: {', '.join(f'`{skill}`' for skill in agent.skills)}",
                f"- Evidence: {', '.join(f'`{kind}`' for kind in agent.evidence)}",
                "",
            ]
        )
    return "\n".join(lines)


def validate_catalogue(
    path: Path,
    expected: str,
    error_factory,
) -> None:
    """Require the checked-in catalogue to be byte-identical to regeneration."""
    try:
        actual = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise error_factory(path, "catalogue-readable", str(exc)) from exc
    if actual != expected:
        raise error_factory(
            path,
            "catalogue-drift",
            "regenerate with python scripts/check_agent_registry.py --write-catalogue",
        )
