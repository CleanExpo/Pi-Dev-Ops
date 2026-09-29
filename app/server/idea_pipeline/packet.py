"""One-screen Board packet shaped like existing SPM / Judge / Storm harnesses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .examine import examine_idea
from .intake import RawIdea
from .constants import NORTH_STAR_SOURCE, NORTH_STAR_REVISION


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _judge_block(exam: dict[str, Any], text: str) -> dict[str, Any]:
    return {
        "score": None,
        "decision": "REVIEW_REQUIRED",
        "category_scores": {},
        "note": "No evidence was verified by this deterministic intake. Judge and Board review remain required.",
    }


def _spm_block(idea: RawIdea, exam: dict[str, Any]) -> dict[str, Any]:
    return {
        "problem": idea.text,
        "desired_outcome": (
            "A one-word dispose on a Board packet. Nothing starts without GO."
        ),
        "in_scope": "Examine, packet, dispose, GO gate.",
        "out_of_scope": "Auto-starting the machine spec pipeline or any paid fallback.",
        "directive": exam["directive"]["label"],
    }


def _storm_block(idea: RawIdea, exam: dict[str, Any]) -> dict[str, Any]:
    rows = [
        {
            "claim": f"Nexus North Star: {exam['north_star_fit']['north_star']}",
            "source_title": f"{NORTH_STAR_SOURCE} ({NORTH_STAR_REVISION})",
            "status": "SUPPORTED",
        },
        {
            "claim": f"Intake is the file {idea.intake_path}",
            "source_title": "IDEAS.md",
            "status": "SUPPORTED",
        },
        {
            "claim": exam["directive"]["rationale"],
            "source_title": "idea_pipeline.constants.DIRECTIVES",
            "status": "UNVERIFIED",
        },
        {
            "claim": "SPM / Judge / Storm already exist as estate patterns",
            "source_title": ".spm / .judge / spec_pipeline",
            "status": "SUPPORTED",
        },
    ]
    return {"rows": rows, "note": "Repo-grounded only. No paid retrieval."}


def build_packet(idea: RawIdea, others: list[RawIdea] | None = None) -> dict[str, Any]:
    exam = examine_idea(idea, others)
    return {
        "idea_id": idea.idea_id,
        "text": idea.text,
        "source": idea.source,
        "intake_path": idea.intake_path,
        "created_at": _iso_now(),
        "status": "awaiting_dispose",
        "verdict": None,
        "disposed_at": None,
        "go_at": None,
        "execution_requested": False,
        "executed": False,
        "recommended_verdict": exam["recommended_verdict"],
        "north_star_fit": exam["north_star_fit"],
        "effort_vs_impact": exam["effort_vs_impact"],
        "directive": exam["directive"],
        "displacement": exam["displacement"],
        "judge": _judge_block(exam, idea.text),
        "spm": _spm_block(idea, exam),
        "storm": _storm_block(idea, exam),
    }
