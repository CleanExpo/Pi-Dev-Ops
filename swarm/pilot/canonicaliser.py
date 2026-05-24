"""PillarCanonicaliser — maps source-native identifiers to master pillars.

Per ADR 001 — sources delegate; canonicaliser owns translation. Returns ≥1
master pillars from the wiki-frontmatter list; falls back to ['uncategorised'].
No source carries its own pillar enum.
"""
from swarm.pilot.wiki_frontmatter import load_master_pillars

_LINEAR_TEAM_MAP: dict[str, str] = {
    "RA": "Restoration", "DR": "Restoration", "NRPG": "Restoration",
    "CCW": "Carpet", "CARSI": "CARSI", "ATIA": "ATIA Meta",
    "UG": "Tier-2 Infra", "SYN": "Tier-2 Infra",
}


class PillarCanonicaliser:
    def __init__(self):
        self._master: frozenset[str] = frozenset(load_master_pillars())

    def _resolve(self, candidate: str) -> list[str]:
        return [candidate] if candidate in self._master else ["uncategorised"]

    def canonicalise_linear(self, team_key: str | None) -> list[str]:
        if not team_key:
            return ["uncategorised"]
        mapped = _LINEAR_TEAM_MAP.get(team_key)
        return self._resolve(mapped) if mapped else ["uncategorised"]

    def canonicalise_margot(self, vertical: str | None) -> list[str]:
        if vertical and vertical in self._master:
            return [vertical]
        return ["Margot"] if "Margot" in self._master else ["uncategorised"]

    def canonicalise_github(self, repo: str | None) -> list[str]:
        return ["Tier-2 Infra"] if "Tier-2 Infra" in self._master else ["uncategorised"]

    def canonicalise_gmail(self, message_id: str | None) -> list[str]:
        return ["uncategorised"]

    def canonicalise_wiki(self, slug: str | None) -> list[str]:
        return ["Wiki"] if "Wiki" in self._master else ["uncategorised"]
