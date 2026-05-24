"""Linear — stale in-flight epics via Composio CLI.

Per ADR 001: no local team-to-pillar constant. Delegates to PillarCanonicaliser.
'stale-in-flight' = >7d since updatedAt; distinct from github_source stale-green.
"""
import subprocess
import json
from datetime import datetime, timezone, timedelta

from swarm.pilot.types import RawCandidate
from swarm.pilot.canonicaliser import PillarCanonicaliser

STALE_IN_FLIGHT_DAYS = 7


def _fetch_in_flight_epics() -> list[dict]:
    try:
        r = subprocess.run(
            ["composio", "execute", "linear_list_issues",
             "--state", "In Progress", "--limit", "20"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(r.stdout).get("issues", [])
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def _is_stale(updated_at: str) -> bool:
    u = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - u) > timedelta(days=STALE_IN_FLIGHT_DAYS)


def collect() -> list[RawCandidate]:
    can = PillarCanonicaliser()
    out: list[RawCandidate] = []
    for i in _fetch_in_flight_epics():
        if not _is_stale(i["updatedAt"]):
            continue
        team_key = i.get("team", {}).get("key")
        out.append(RawCandidate(
            fingerprint=f"linear:stale_epic:{i['id']}",
            headline=f"{i['id']} ({team_key}) stale {STALE_IN_FLIGHT_DAYS}d — review or close?",
            pillar=can.canonicalise_linear(team_key),
            effort="S", source="linear", confidence="MED",
            body={"issue": i}, impact_score=60,
        ))
    return out
