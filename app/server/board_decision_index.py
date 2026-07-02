"""RA-6907 — queryable board decision index + mandate consistency gate.

Extracts locked conditions from `.harness/board-meetings/*.md` and rejects
mandates that explicitly overturn them (deterministic negation patterns).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_NEGATION_RE = re.compile(
    r"\b("
    r"remove|disable|lift|bypass|repeal|overturn|delete|drop|eliminate|"
    r"unlimited|unrestricted|no\s+limit|without\s+limit|stop\s+enforcing"
    r")\b",
    re.IGNORECASE,
)

_CONDITIONS_HEADING_RE = re.compile(
    r"^##\s+Conditions\s+Locked\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SECTION_RE = re.compile(r"^###\s+\d+\.\s+(.+)$", re.MULTILINE)


@dataclass
class BoardDecision:
    decision_id: str
    title: str
    body: str
    source_file: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class MandateConsistencyResult:
    allowed: bool
    contradictions: list[dict[str, str]] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.allowed:
            return "consistent"
        parts = [
            f"{c['decision_id']}: {c['detail']}"
            for c in self.contradictions
        ]
        return "; ".join(parts)


def _tokenize(text: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_/-]{2,}", text)
        if w.lower() not in {"the", "and", "for", "with", "that", "this", "from"}
    }


def _extract_locked_sections(content: str, source: str) -> list[BoardDecision]:
    decisions: list[BoardDecision] = []
    if not _CONDITIONS_HEADING_RE.search(content):
        return decisions

    start = _CONDITIONS_HEADING_RE.search(content)
    if not start:
        return decisions
    section = content[start.end() :]

    # Split on ### N. headings within the locked block (until next ## heading)
    next_h2 = re.search(r"^##\s+", section, re.MULTILINE)
    if next_h2:
        section = section[: next_h2.start()]

    matches = list(_SECTION_RE.finditer(section))
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        body = section[body_start:body_end].strip()
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or f"item-{idx + 1}"
        decisions.append(
            BoardDecision(
                decision_id=f"{source}:{slug}",
                title=title,
                body=body,
                source_file=source,
                keywords=sorted(_tokenize(title + " " + body)),
            )
        )
    return decisions


def build_decision_index(meetings_dir: Path | None = None) -> list[BoardDecision]:
    """Load locked board decisions from harness board-meeting markdown."""
    if meetings_dir is None:
        meetings_dir = Path(__file__).resolve().parents[2] / ".harness" / "board-meetings"
    if not meetings_dir.is_dir():
        return []

    index: list[BoardDecision] = []
    for path in sorted(meetings_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        index.extend(_extract_locked_sections(content, path.name))
    return index


def _mandate_contradicts_decision(mandate: str, decision: BoardDecision) -> str | None:
    mandate_lower = mandate.lower()
    if not _NEGATION_RE.search(mandate):
        return None

    decision_tokens = set(decision.keywords)
    mandate_tokens = _tokenize(mandate)
    overlap = decision_tokens & mandate_tokens
    if len(overlap) < 2:
        return None

    # Strong signal: numeric limits in decision referenced with negation in mandate
    numbers_in_decision = set(re.findall(r"\b\d+\b", decision.title + decision.body))
    if numbers_in_decision:
        for num in numbers_in_decision:
            if num in mandate and _NEGATION_RE.search(mandate):
                return (
                    f"mandate negates locked condition '{decision.title}' "
                    f"(shared terms: {', '.join(sorted(overlap)[:5])})"
                )

    if len(overlap) >= 3:
        return (
            f"mandate may overturn locked condition '{decision.title}' "
            f"(shared terms: {', '.join(sorted(overlap)[:5])})"
        )
    return None


def check_mandate_consistency(
    mandate: str,
    index: list[BoardDecision] | None = None,
    *,
    meetings_dir: Path | None = None,
) -> MandateConsistencyResult:
    """Return allowed=False when mandate explicitly contradicts a locked decision."""
    text = (mandate or "").strip()
    if not text:
        return MandateConsistencyResult(allowed=True)

    decisions = index if index is not None else build_decision_index(meetings_dir)
    contradictions: list[dict[str, str]] = []
    for decision in decisions:
        detail = _mandate_contradicts_decision(text, decision)
        if detail:
            contradictions.append(
                {
                    "decision_id": decision.decision_id,
                    "title": decision.title,
                    "source_file": decision.source_file,
                    "detail": detail,
                }
            )

    return MandateConsistencyResult(
        allowed=len(contradictions) == 0,
        contradictions=contradictions,
    )
