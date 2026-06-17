"""Specialist routing for Telegram-originated swarm work.

This is the layer after intent classification. ``intent_router`` decides what
the founder is asking for; this module decides which specialist lane should own
the next action so Telegram can behave like a mobile command surface instead of
a single undifferentiated inbox.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Literal


Specialist = Literal[
    "margot",
    "board",
    "builder",
    "cto",
    "cmo",
    "cfo",
    "cs",
    "research",
    "ops",
    "scribe",
]


@dataclass(frozen=True)
class SpecialistRoute:
    specialist: Specialist
    persona: str
    action: str
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_COMMAND_ROUTES: dict[str, SpecialistRoute] = {
    "/margot": SpecialistRoute("margot", "Margot", "personal_assistant_turn", 0.99, "explicit /margot command"),
    "/board": SpecialistRoute("board", "Board", "board_review", 0.99, "explicit /board command"),
    "/builder": SpecialistRoute("builder", "Builder", "autonomous_build_triage", 0.99, "explicit /builder command"),
    "/dev": SpecialistRoute("builder", "Builder", "autonomous_build_triage", 0.98, "explicit /dev command"),
    "/cto": SpecialistRoute("cto", "CTO", "technical_strategy", 0.99, "explicit /cto command"),
    "/cmo": SpecialistRoute("cmo", "CMO", "growth_strategy", 0.99, "explicit /cmo command"),
    "/cfo": SpecialistRoute("cfo", "CFO", "finance_review", 0.99, "explicit /cfo command"),
    "/cs": SpecialistRoute("cs", "CS", "customer_success_review", 0.99, "explicit /cs command"),
    "/ops": SpecialistRoute("ops", "Ops", "operational_triage", 0.99, "explicit /ops command"),
    "/scribe": SpecialistRoute("scribe", "Scribe", "capture_and_summarise", 0.99, "explicit /scribe command"),
    "/research": SpecialistRoute("research", "Research", "research_brief", 0.99, "explicit /research command"),
}


_KEYWORD_ROUTES: list[tuple[re.Pattern[str], SpecialistRoute]] = [
    (
        re.compile(r"\b(ci|deploy|vercel|railway|github action|production|incident|outage|latency|api|architecture|technical|security)\b", re.I),
        SpecialistRoute("cto", "CTO", "technical_strategy", 0.82, "technical/platform keyword match"),
    ),
    (
        re.compile(r"\b(build|fix|ship|implement|pr|pull request|merge|test|commit|linear task|ticket)\b", re.I),
        SpecialistRoute("builder", "Builder", "autonomous_build_triage", 0.80, "build/delivery keyword match"),
    ),
    (
        re.compile(r"\b(marketing|campaign|lead|funnel|conversion|content|seo|ad|brand|launch)\b", re.I),
        SpecialistRoute("cmo", "CMO", "growth_strategy", 0.78, "growth keyword match"),
    ),
    (
        re.compile(r"\b(cost|budget|runway|revenue|margin|invoice|billing|cash|forecast)\b", re.I),
        SpecialistRoute("cfo", "CFO", "finance_review", 0.78, "finance keyword match"),
    ),
    (
        re.compile(r"\b(client|customer|support|nps|complaint|onboarding|retention|churn)\b", re.I),
        SpecialistRoute("cs", "CS", "customer_success_review", 0.78, "customer-success keyword match"),
    ),
    (
        re.compile(r"\b(research|latest|market|competitor|paper|repo|hugging ?face|github creator|trend)\b", re.I),
        SpecialistRoute("research", "Research", "research_brief", 0.78, "research keyword match"),
    ),
    (
        re.compile(r"\b(decide|approve|priority|northstar|strategy|risk|tradeoff|board)\b", re.I),
        SpecialistRoute("board", "Board", "board_review", 0.76, "governance keyword match"),
    ),
    (
        re.compile(r"\b(note|capture|summary|summarise|transcript|obsidian|second brain|2nd brain|plaud)\b", re.I),
        SpecialistRoute("scribe", "Scribe", "capture_and_summarise", 0.76, "capture/knowledge keyword match"),
    ),
]


def route_message(message_text: str, intent_payload: dict[str, Any] | None = None) -> SpecialistRoute:
    """Choose the specialist lane for a Telegram message.

    Command prefixes win, then high-signal intents, then keyword fallback. The
    result is deterministic and serialisable so it can be attached to the
    canonical intent payload and shown in draft-review cards.
    """
    text = (message_text or "").strip()
    lowered = text.lower()
    first_token = lowered.split(maxsplit=1)[0] if lowered else ""

    if first_token in _COMMAND_ROUTES:
        return _COMMAND_ROUTES[first_token]

    intent = (intent_payload or {}).get("intent")
    if intent == "margot":
        return SpecialistRoute("margot", "Margot", "personal_assistant_turn", 0.96, "margot intent")
    if intent == "research":
        return SpecialistRoute("research", "Research", "research_brief", 0.88, "research intent")
    if intent == "fix_project":
        return SpecialistRoute("builder", "Builder", "autonomous_build_triage", 0.88, "fix_project intent")
    if intent == "ticket":
        return SpecialistRoute("ops", "Ops", "operational_triage", 0.82, "ticket intent")
    if intent == "reminder":
        return SpecialistRoute("ops", "Ops", "operational_triage", 0.80, "reminder intent")
    if intent == "reply":
        return SpecialistRoute("scribe", "Scribe", "capture_and_summarise", 0.76, "reply intent")

    for pattern, route in _KEYWORD_ROUTES:
        if pattern.search(text):
            return route

    return SpecialistRoute("margot", "Margot", "personal_assistant_turn", 0.55, "default founder assistant fallback")


def attach_route(intent_payload: dict[str, Any], message_text: str | None = None) -> dict[str, Any]:
    """Return a copy of ``intent_payload`` with ``specialist_route`` attached."""
    text = message_text
    if text is None:
        text = str(intent_payload.get("raw_message") or "")
    route = route_message(text, intent_payload)
    return {**intent_payload, "specialist_route": route.to_dict()}


__all__ = ["SpecialistRoute", "attach_route", "route_message"]
