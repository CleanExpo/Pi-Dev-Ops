"""
skill_router.py — pick the skill a request needs, load only that one, carry nothing forward.

Order per request:
  1. pin       an exact router phrase names its skill; no model call.
  2. shortlist free lexical scoring over name + description + the first BODY_SCORE_CHARS of
               the body. A 1:1 port of the skills library's scorer
               (skills/skill-selector/scripts/vendor/skill-router/lib.mjs scoreItem/queryTokens),
               pinned by tests/fixtures/skill_router_parity.json.
  3. pick      one Jev Choice over the shortlist plus NO_MATCH. NO_MATCH or low confidence
               loads nothing.
  4. load      only the chosen body, cut to the request's token budget.

Jev missing or failing is never hidden: the decision says source="lexical_fallback" and why.
Nothing here keeps a body between requests; each prompt gets what its request chose.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Callable

BODY_SCORE_CHARS = 8000  # lib.mjs BODY_SCORE_CHARS
NO_MATCH = "NO_MATCH"
CUT_MARK = "\n[... cut to the skill budget]"
CHARS_PER_TOKEN = 4
SHORTLIST = 20
MAX_OPTIONS = 254  # Jev allows 255 options per Choice; one is NO_MATCH
DESC_CHARS = 160  # per option in the Jev question; keeps a 254-option question near 11k tokens
MIN_CONFIDENCE = 0.5
DEFAULT_BUDGET = 2000

# lib.mjs STOPWORDS: filtered from the query only, never the haystack.
STOPWORDS = frozenset(
    "the a an my me i you your to for of in on with and or is are it this that how do does can want "
    "need help please make get set up use using when what which some more so at be".split()
)
_WORD = re.compile(r"\w+", re.ASCII)  # JS /\w+/g is ASCII-only
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD.findall(text)}


def query_tokens(text: str) -> set[str]:
    all_tokens = tokens(text)
    kept = {t for t in all_tokens if t not in STOPWORDS and len(t) > 1}
    return kept or all_tokens


@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    haystack: str  # lower-cased name + description + body prefix: search text, not prompt text
    haystack_tokens: frozenset[str]

    @classmethod
    def from_parts(cls, name: str, description: str, body: str) -> "Candidate":
        hay = "\n".join([name, description, body[:BODY_SCORE_CHARS]]).lower()
        return cls(name, description, hay, frozenset(tokens(hay)))


def score(c: Candidate, q_tokens: set[str], query_text: str) -> float:
    """lib.mjs scoreItem, term for term."""
    s = float(sum(1 for t in q_tokens if t in c.haystack_tokens))
    if query_text and query_text in c.haystack:
        s += 5
    name, desc = c.name.lower(), c.description.lower()
    fragments = [n for n in _NON_ALNUM.split(name) if len(n) >= 3]
    for t in q_tokens:
        if t in name:
            s += 3
        elif any(n in t for n in fragments):
            s += 2
        if t in desc:
            s += 1.5
    if s == 0:
        return 0
    return s + 1 / math.sqrt(max(len(c.haystack_tokens), 1))


def build_catalogue(skills: dict[str, dict]) -> list[Candidate]:
    return [Candidate.from_parts(s["name"], str(s.get("description", "")), s.get("body", "")) for s in skills.values()]


def shortlist(text: str, catalogue: list[Candidate], k: int = SHORTLIST) -> list[tuple[str, float]]:
    q = text.lower().strip()
    qt = query_tokens(q)
    scored = [(c.name, score(c, qt, q)) for c in catalogue]
    return sorted([x for x in scored if x[1] > 0], key=lambda x: -x[1])[:k]


@dataclass
class RouteDecision:
    skills: list[str] = field(default_factory=list)
    bodies: list[str] = field(default_factory=list)
    source: str = "none"  # pin | jev | lexical_fallback | none
    confidence: float | None = None
    tokens: int = 0
    jev_input_tokens: int = 0
    reason: str = ""
    shortlist: list[str] = field(default_factory=list)


def _load(decision: RouteDecision, name: str, skills: dict[str, dict], budget_tokens: int) -> RouteDecision:
    body = skills[name].get("body", "")
    limit = budget_tokens * CHARS_PER_TOKEN
    if len(body) > limit:
        # A budget too small to hold the mark gets nothing, never a body over budget.
        body = body[: limit - len(CUT_MARK)] + CUT_MARK if limit >= len(CUT_MARK) else ""
    decision.skills, decision.bodies = [name], [body]
    decision.tokens = math.ceil(len(body) / CHARS_PER_TOKEN)
    return decision


def jev_payload(text: str, options: list[tuple[str, str]]) -> dict:
    from scripts.mission_control_jev_shadow import MODEL, redact

    criteria = {name: desc[:DESC_CHARS] or name for name, desc in options[:MAX_OPTIONS]}
    criteria[NO_MATCH] = "None of these skills fits the request."
    return {
        "model": MODEL,
        "state": {"request": redact(text)[:4000]},
        "questions": {"skill": {"type": "choice", "instructions": "Which skill does `request` need?",
                                "criteria": criteria}},
    }


def route(
    text: str,
    *,
    catalogue: list[Candidate],
    skills: dict[str, dict],
    jev: Callable[[dict], dict] | None,
    pins: dict[str, str] | None = None,
    budget_tokens: int = DEFAULT_BUDGET,
    k: int = SHORTLIST,
    min_confidence: float = MIN_CONFIDENCE,
) -> RouteDecision:
    pinned = (pins or {}).get(text.lower().strip())
    if pinned and pinned in skills:
        return _load(RouteDecision(source="pin", reason="router_phrase"), pinned, skills, budget_tokens)

    short = shortlist(text, catalogue, min(k, MAX_OPTIONS))
    decision = RouteDecision(shortlist=[n for n, _ in short])
    if not short:
        decision.reason = "nothing_scored"
        return decision
    if jev is None:
        decision.source, decision.reason = "lexical_fallback", "jev_unavailable"
        return _load(decision, short[0][0], skills, budget_tokens)
    by_name = {c.name: c for c in catalogue}
    payload = jev_payload(text, [(n, by_name[n].description) for n, _ in short])
    return _jev_pick(decision, payload, jev, skills, budget_tokens, min_confidence)


def _jev_pick(
    decision: RouteDecision,
    payload: dict,
    jev: Callable[[dict], dict],
    skills: dict[str, dict],
    budget_tokens: int,
    min_confidence: float,
) -> RouteDecision:
    from scripts.mission_control_jev_shadow import validate_answer

    try:
        result = jev(payload)
        answer = validate_answer("skill", result["answers"].get("skill"), payload["questions"]["skill"])
        if answer is None:
            raise ValueError("malformed Jev answer")
        choice, confidence = answer["label"], float(answer["confidence"])
        decision.jev_input_tokens = int(result.get("usage", {}).get("input_tokens", 0))
    except Exception as exc:  # any Jev failure degrades visibly, never silently
        decision.source, decision.reason = "lexical_fallback", f"jev_error:{type(exc).__name__}"
        return _load(decision, decision.shortlist[0], skills, budget_tokens)
    return apply_answer(decision, choice, confidence, skills, budget_tokens, min_confidence)


def apply_answer(
    decision: RouteDecision,
    choice: str,
    confidence: float,
    skills: dict[str, dict],
    budget_tokens: int,
    min_confidence: float = MIN_CONFIDENCE,
) -> RouteDecision:
    """The one rule for turning a Jev answer into what gets loaded; the eval runner uses it too."""
    decision.source, decision.confidence = "jev", confidence
    if choice == NO_MATCH:
        decision.reason = "no_match"
        return decision
    if choice not in skills or choice not in decision.shortlist:
        decision.reason = "jev_answer_outside_shortlist"
        return decision
    if confidence < min_confidence:
        decision.reason = "low_confidence"
        return decision
    decision.reason = "picked"
    return _load(decision, choice, skills, budget_tokens)


def default_jev() -> Callable[[dict], dict] | None:
    """Live Jev only when a key is present in this process's environment; otherwise None."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return None
    from scripts.mission_control_jev_shadow import evaluate

    return lambda payload: evaluate(payload, key)
