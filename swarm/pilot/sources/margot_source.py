"""Margot research queue — pending deep-research items as suggestions.

Per ADR 001: NO local _VALID_PILLARS. Delegates to PillarCanonicaliser.
"""
import os

from swarm.pilot.types import RawCandidate
from swarm.pilot.canonicaliser import PillarCanonicaliser


def _supabase_client():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def collect() -> list[RawCandidate]:
    try:
        rows = (
            _supabase_client()
            .table("margot_research_queue")
            .select("id,topic,status,vertical")
            .eq("status", "pending")
            .execute()
            .data or []
        )
    except Exception:
        return []
    can = PillarCanonicaliser()
    return [
        RawCandidate(
            fingerprint=f"margot:research:{r['id']}",
            headline=f"Margot research pending: {r['topic'][:60]} — dispatch?",
            pillar=can.canonicalise_margot(r.get("vertical")),
            effort="S", source="margot", confidence="MED",
            body={"queue_row": r}, impact_score=55,
        )
        for r in rows
    ]
