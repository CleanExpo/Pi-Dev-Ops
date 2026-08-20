"""Intent-only YouTube catalog and synthesis for UG-N Nexus.

This module intentionally stores only strategic research signals.
Personal/entertainment items are excluded by default unless manually overridden.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path(".harness/ugn_intent_youtube/state.json")
POLICY_PATH = Path("config/harness/youtube_intent_policy.json")
WIKI_DIR = Path("brain/ug-nexus")

STRATEGIC_KEYWORDS = (
    "ai",
    "automation",
    "agent",
    "workflow",
    "product",
    "startup",
    "growth",
    "strategy",
    "operations",
    "sales",
    "marketing",
    "finance",
    "analytics",
    "leadership",
    "system",
    "research",
    "innovation",
    "platform",
    "saas",
    "customer",
    "funnel",
)

ENTERTAINMENT_KEYWORDS = (
    "music",
    "song",
    "movie",
    "trailer",
    "vlog",
    "gaming",
    "comedy",
    "reaction",
    "prank",
    "celebrity",
    "podcast clip",
    "meme",
    "highlights",
)

TOPIC_TO_VERTICAL = {
    "ai": "ai-and-automation",
    "automation": "ai-and-automation",
    "agent": "ai-and-automation",
    "workflow": "ai-and-automation",
    "sales": "growth-engine",
    "marketing": "growth-engine",
    "growth": "growth-engine",
    "funnel": "growth-engine",
    "finance": "capital-and-ops",
    "analytics": "capital-and-ops",
    "operations": "capital-and-ops",
    "leadership": "leadership-and-vision",
    "strategy": "leadership-and-vision",
    "innovation": "leadership-and-vision",
}


@dataclass
class CatalogResult:
    accepted: int
    excluded: int
    total: int
    status_breakdown: dict[str, int]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def default_policy() -> dict[str, Any]:
    return {
        "version": 1,
        "name": "intent_only_strategic_policy",
        "include_if": [
            "selected_by_user == true",
            "contains strategic keyword",
            "channel/title/tags match business taxonomy",
        ],
        "exclude_if": [
            "contains entertainment keyword and no strategic keyword",
            "explicit force_exclude == true",
            "ambiguous relevance without force_include",
        ],
        "manual_overrides": ["force_include", "force_exclude"],
        "updated_at": _now(),
    }


def ensure_policy() -> dict[str, Any]:
    policy = _read_json(POLICY_PATH, default_policy())
    if not POLICY_PATH.exists():
        _write_json(POLICY_PATH, policy)
    return policy


def default_state() -> dict[str, Any]:
    return {
        "updated_at": _now(),
        "videos": [],
        "topics": [],
        "persona_traits": [],
        "vertical_pathway_signals": [],
        "wiki_pages": [],
    }


def load_state() -> dict[str, Any]:
    return _read_json(STATE_PATH, default_state())


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    _write_json(STATE_PATH, state)


def _to_blob(item: dict[str, Any]) -> str:
    parts = [
        item.get("title", ""),
        item.get("channel", ""),
        item.get("description", ""),
        " ".join(item.get("tags", []) or []),
    ]
    return " ".join(parts).lower()


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def classify_item(item: dict[str, Any]) -> dict[str, Any]:
    blob = _to_blob(item)
    words = _word_set(blob)
    strategic_hits = sorted(k for k in STRATEGIC_KEYWORDS if k in words or k in blob)
    entertainment_hits = sorted(k for k in ENTERTAINMENT_KEYWORDS if k in words or k in blob)
    selected = bool(item.get("selected_by_user"))
    force_include = bool(item.get("force_include"))
    force_exclude = bool(item.get("force_exclude"))
    watch_count = max(1, int(item.get("watch_count_window", 1)))

    if force_exclude:
        status = "excluded"
        reason = "manual_force_exclude"
    elif force_include:
        status = "accepted"
        reason = "manual_force_include"
    elif strategic_hits:
        status = "accepted"
        reason = "strategic_match"
    elif selected and not entertainment_hits:
        status = "accepted"
        reason = "selected_user_seed"
    elif entertainment_hits:
        status = "excluded"
        reason = "entertainment_signal"
    else:
        status = "excluded"
        reason = "ambiguous_not_strategic"

    return {
        **item,
        "status": status,
        "reason": reason,
        "watch_count_window": watch_count,
        "strategic_hits": strategic_hits,
        "entertainment_hits": entertainment_hits,
        "ingested_at": _now(),
    }


def upsert_catalog(items: list[dict[str, Any]]) -> CatalogResult:
    state = load_state()
    existing = {row["video_key"]: row for row in state.get("videos", [])}
    statuses: Counter[str] = Counter()
    for raw in items:
        video_key = str(raw.get("video_id") or raw.get("url") or raw.get("title") or "").strip()
        if not video_key:
            continue
        normalized = classify_item({**raw, "video_key": video_key})
        existing[video_key] = normalized
        statuses.update([normalized["status"]])

    ordered = sorted(
        existing.values(),
        key=lambda row: (
            0 if row.get("status") == "accepted" else 1,
            -int(row.get("watch_count_window", 1)),
            row.get("title", ""),
        ),
    )
    state["videos"] = ordered
    save_state(state)
    return CatalogResult(
        accepted=statuses.get("accepted", 0),
        excluded=statuses.get("excluded", 0),
        total=sum(statuses.values()),
        status_breakdown=dict(statuses),
    )


def _vertical_for_topic(topic: str) -> str:
    return TOPIC_TO_VERTICAL.get(topic, "exploratory")


def synthesize_state() -> dict[str, Any]:
    state = load_state()
    accepted = [r for r in state.get("videos", []) if r.get("status") == "accepted"]
    topic_scores: dict[str, float] = defaultdict(float)
    topic_evidence: dict[str, list[str]] = defaultdict(list)

    for row in accepted:
        score = float(row.get("watch_count_window", 1))
        for topic in row.get("strategic_hits", [])[:5]:
            topic_scores[topic] += score
            topic_evidence[topic].append(row.get("title", row["video_key"]))

    topics = sorted(topic_scores.items(), key=lambda kv: kv[1], reverse=True)
    state["topics"] = [
        {
            "topic": topic,
            "frequency_score": round(score, 2),
            "confidence": round(min(0.95, 0.4 + score / 20.0), 2),
            "evidence_titles": topic_evidence[topic][:5],
        }
        for topic, score in topics
    ]

    persona = []
    for topic, score in topics[:8]:
        persona.append(
            {
                "trait": f"High focus on {topic}",
                "confidence": round(min(0.95, 0.45 + score / 24.0), 2),
                "evidence_topic": topic,
            }
        )
    state["persona_traits"] = persona

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in state["topics"]:
        grouped[_vertical_for_topic(entry["topic"])].append(entry)
    verticals = []
    for vertical, entries in grouped.items():
        verticals.append(
            {
                "vertical_id": vertical,
                "direction_theme": ", ".join(e["topic"] for e in entries[:3]),
                "strategic_priority": round(sum(float(e["frequency_score"]) for e in entries), 2),
                "supporting_topics": [e["topic"] for e in entries],
                "candidate_actions": [
                    f"Run one experiment in {entries[0]['topic']} for {vertical}"
                ] if entries else [],
            }
        )
    state["vertical_pathway_signals"] = sorted(verticals, key=lambda v: -v["strategic_priority"])
    pages = write_wiki_pages(state)
    state["wiki_pages"] = pages
    save_state(state)
    return state


def write_wiki_pages(state: dict[str, Any]) -> list[str]:
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    persona_path = WIKI_DIR / "persona_profile.md"
    knowledge_path = WIKI_DIR / "knowledge_map.md"
    verticals_path = WIKI_DIR / "vertical_pathways.md"
    signals_path = WIKI_DIR / "signals_log.md"

    persona_lines = ["# UG-N Persona Profile", "", f"_Updated: {state['updated_at']}_", ""]
    for trait in state.get("persona_traits", []):
        persona_lines.append(f"- {trait['trait']} (confidence {trait['confidence']})")
    persona_path.write_text("\n".join(persona_lines) + "\n", encoding="utf-8")

    knowledge_lines = ["# UG-N Knowledge Map", "", f"_Updated: {state['updated_at']}_", ""]
    for topic in state.get("topics", []):
        evidence = "; ".join(topic.get("evidence_titles", []))
        knowledge_lines.append(
            f"- **{topic['topic']}** · score {topic['frequency_score']} · confidence {topic['confidence']}"
        )
        if evidence:
            knowledge_lines.append(f"  - evidence: {evidence}")
    knowledge_path.write_text("\n".join(knowledge_lines) + "\n", encoding="utf-8")

    vertical_lines = ["# UG-N Vertical Pathways", "", f"_Updated: {state['updated_at']}_", ""]
    for signal in state.get("vertical_pathway_signals", []):
        vertical_lines.append(
            f"- **{signal['vertical_id']}** · priority {signal['strategic_priority']} · theme: {signal['direction_theme']}"
        )
    verticals_path.write_text("\n".join(vertical_lines) + "\n", encoding="utf-8")

    signal_lines = ["# UG-N Signals Log", "", f"_Updated: {state['updated_at']}_", ""]
    for row in state.get("videos", []):
        signal_lines.append(
            f"- {row.get('status', 'unknown').upper()} | {row.get('title', row['video_key'])} | "
            f"watch_count={row.get('watch_count_window', 1)} | reason={row.get('reason', 'n/a')}"
        )
    signals_path.write_text("\n".join(signal_lines) + "\n", encoding="utf-8")
    return [str(persona_path), str(knowledge_path), str(verticals_path), str(signals_path)]


def build_excalidraw_nodes(state: dict[str, Any]) -> dict[str, Any]:
    accepted = len([v for v in state.get("videos", []) if v.get("status") == "accepted"])
    excluded = len([v for v in state.get("videos", []) if v.get("status") == "excluded"])
    topics = len(state.get("topics", []))
    traits = len(state.get("persona_traits", []))
    verticals = len(state.get("vertical_pathway_signals", []))

    return {
        "status": {
            "signalSources": "validated" if accepted else "new",
            "relevanceFilter": "validated" if excluded or accepted else "new",
            "personaModel": "validated" if traits else "needs_review",
            "verticalPathways": "validated" if verticals else "needs_review",
            "wikiOutputs": "validated" if state.get("wiki_pages") else "needs_review",
        },
        "metrics": {
            "acceptedSignals": accepted,
            "excludedSignals": excluded,
            "topics": topics,
            "personaTraits": traits,
            "verticalSignals": verticals,
        },
        "updated_at": state.get("updated_at"),
    }
