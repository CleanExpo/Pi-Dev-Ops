"""Wiki — stale pages as suggestions to review or update.

Per ADR 001: pillar always ["Wiki"] via canonicalise_wiki().
Wiki slugs don't canonicalise to business pillars — they ARE the wiki pillar.
"""
import subprocess
import json

from swarm.pilot.types import RawCandidate
from swarm.pilot.canonicaliser import PillarCanonicaliser

STALE_DAYS = 30


def _fetch_stale_pages() -> list[dict]:
    try:
        r = subprocess.run(
            ["python", "-m", "swarm.wiki.cli", "list-stale",
             "--days", str(STALE_DAYS), "--limit", "20"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(r.stdout).get("pages", [])
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def collect() -> list[RawCandidate]:
    can = PillarCanonicaliser()
    out: list[RawCandidate] = []
    for page in _fetch_stale_pages():
        slug = page["slug"]
        out.append(RawCandidate(
            fingerprint=f"wiki:stale_page:{slug}",
            headline=f"Wiki page '{slug}' stale {page.get('days_since_edit', STALE_DAYS)}d — review or archive?",
            pillar=can.canonicalise_wiki(slug),
            effort="S", source="wiki", confidence="LOW",
            body={"page": page}, impact_score=25,
        ))
    return out
