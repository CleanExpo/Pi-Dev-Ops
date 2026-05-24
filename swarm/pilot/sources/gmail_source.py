"""Gmail — unactioned threads as suggestions.

Per ADR 001: pillar always ["uncategorised"] — Gmail labels don't map
to strategic pillars. Delegates to PillarCanonicaliser.canonicalise_gmail().
"""
import subprocess
import json

from swarm.pilot.types import RawCandidate
from swarm.pilot.canonicaliser import PillarCanonicaliser


def _fetch_unactioned_threads() -> list[dict]:
    try:
        r = subprocess.run(
            ["composio", "execute", "gmail_list_threads",
             "--label", "INBOX", "--limit", "20"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(r.stdout).get("threads", [])
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def collect() -> list[RawCandidate]:
    can = PillarCanonicaliser()
    out: list[RawCandidate] = []
    for thread in _fetch_unactioned_threads():
        label = thread.get("label", "INBOX")
        out.append(RawCandidate(
            fingerprint=f"gmail:thread:{thread['id']}",
            headline=f"Unactioned email: {thread.get('snippet', '')[:60]}",
            pillar=can.canonicalise_gmail(label),
            effort="XS", source="gmail", confidence="LOW",
            body={"thread": thread}, impact_score=30,
        ))
    return out
