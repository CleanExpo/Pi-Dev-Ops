"""Deterministic Board exam — no paid models, Max-plan later if needed."""

from __future__ import annotations

import re
from typing import Any

from .constants import (
    ACTION_VERBS,
    DIRECTIVES,
    HIGH_EFFORT,
    LOW_EFFORT,
    NORTH_STAR,
    NORTH_STAR_TERMS,
)
from .intake import RawIdea

_WORD = re.compile(r"[a-z0-9][a-z0-9-]{1,}")


def tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def north_star_fit(text: str) -> dict[str, Any]:
    words = tokens(text)
    hits = sorted(words & NORTH_STAR_TERMS)
    score = min(1.0, len(hits) / 4.0)
    if score >= 0.75:
        label = "strong"
    elif score >= 0.4:
        label = "partial"
    else:
        label = "weak"
    why = (
        f"Matched {', '.join(hits)} against the North Star."
        if hits
        else "No North Star words found."
    )
    return {
        "score": round(score, 2),
        "label": label,
        "hits": hits,
        "north_star": NORTH_STAR,
        "rationale": why,
    }


def effort_vs_impact(text: str, fit: dict[str, Any]) -> dict[str, Any]:
    words = tokens(text)
    if words & HIGH_EFFORT:
        effort = "high"
    elif words & LOW_EFFORT:
        effort = "low"
    else:
        effort = "medium"
    impact = "high" if fit["score"] >= 0.6 else "medium" if fit["score"] >= 0.35 else "low"
    return {
        "effort": effort,
        "impact": impact,
        "rationale": (
            f"Effort reads {effort} from the wording; impact reads {impact} "
            f"from North Star fit {fit['score']:.2f}."
        ),
    }


def which_directive(text: str) -> dict[str, Any]:
    lowered = text.lower()
    scored: list[tuple[int, str, str]] = []
    for dir_id, label, cues in DIRECTIVES:
        hits = sum(1 for cue in cues if cue in lowered)
        if hits:
            scored.append((hits, dir_id, label))
    if not scored:
        return {
            "id": "unmapped",
            "label": "No named directive yet",
            "rationale": "The idea does not name a current directive.",
        }
    scored.sort(reverse=True)
    hits, dir_id, label = scored[0]
    return {
        "id": dir_id,
        "label": label,
        "rationale": f"Serves {label} ({hits} cue hits).",
    }


def what_it_displaces(text: str, others: list[RawIdea]) -> dict[str, Any]:
    words = tokens(text)
    rivals: list[str] = []
    for other in others:
        shared = tokens(other.text) & words
        shared -= {"the", "and", "for", "that", "this", "with", "from"}
        if len(shared) >= 3:
            rivals.append(other.text)
    if rivals:
        return {
            "would_displace": rivals[0],
            "rationale": "Shares enough words with another open idea to compete for the same slot.",
        }
    return {
        "would_displace": "This week's Board slot — nothing else named.",
        "rationale": "No overlapping open idea. Taking it up would still use one Board packet.",
    }


def recommend_verdict(
    fit: dict[str, Any],
    effort: dict[str, Any],
    directive: dict[str, Any],
    text: str,
) -> str:
    words = tokens(text)
    vague = len(text.split()) < 8 or not (words & ACTION_VERBS)
    if fit["score"] < 0.15 and directive["id"] == "unmapped":
        return "KILL"
    if vague:
        return "PARK"
    if fit["score"] >= 0.45 and effort["effort"] != "high" and effort["impact"] != "low":
        return "PROMOTE"
    return "BACKLOG"


def examine_idea(idea: RawIdea, others: list[RawIdea] | None = None) -> dict[str, Any]:
    peers = [item for item in (others or []) if item.idea_id != idea.idea_id]
    fit = north_star_fit(idea.text)
    effort = effort_vs_impact(idea.text, fit)
    directive = which_directive(idea.text)
    displacement = what_it_displaces(idea.text, peers)
    verdict = recommend_verdict(fit, effort, directive, idea.text)
    return {
        "north_star_fit": fit,
        "effort_vs_impact": effort,
        "directive": directive,
        "displacement": displacement,
        "recommended_verdict": verdict,
    }
