"""GitHub — stale-green PRs (green CI, not merged, >18h).

Per ADR 001: delegates pillar to PillarCanonicaliser.
"""
import subprocess
import json

from swarm.pilot.types import RawCandidate
from swarm.pilot.canonicaliser import PillarCanonicaliser

STALE_GREEN_HOURS = 18


def _fetch_stale_green_prs() -> list[dict]:
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--state", "open",
             "--json", "number,title,headRepository,statusCheckRollup,createdAt"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(r.stdout) or []
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def collect() -> list[RawCandidate]:
    can = PillarCanonicaliser()
    out: list[RawCandidate] = []
    for pr in _fetch_stale_green_prs():
        repo = pr.get("repository") or pr.get("headRepository", {}).get("name", "unknown")
        out.append(RawCandidate(
            fingerprint=f"github:stale_green_pr:{repo}:{pr['number']}",
            headline=f"PR #{pr['number']} green {STALE_GREEN_HOURS}h+ — merge or close? ({repo})",
            pillar=can.canonicalise_github(repo),
            effort="XS", source="github", confidence="HIGH",
            body={"pr": pr}, impact_score=75,
        ))
    return out
