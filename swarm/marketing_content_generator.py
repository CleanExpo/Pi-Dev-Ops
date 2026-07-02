"""marketing_content_generator.py — UNI-2236 content generation + eeat/geo gate.

Deterministic quality scoring (no LLM) mirrors eeat + geo-optimization skill
checklists so scheduled runs can emit scored social_posts rows without human
seeding. ICP/positioning context is loaded from marketing-studio frameworks
when present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDIO_ROOT = REPO_ROOT / "marketing-studio"


@dataclass
class IcpContext:
    brand: str
    positioning: str = ""
    icp_summary: str = ""
    source_files: list[str] = field(default_factory=list)


@dataclass
class QualityScores:
    eeat: dict[str, Any]
    geo: dict[str, Any]
    composite: float
    verdict: str  # pass | needs-work | fail


@dataclass
class GeneratedPost:
    business_key: str
    content: str
    title: str
    platforms: list[str]
    hashtags: list[str]
    scores: QualityScores
    metadata: dict[str, Any] = field(default_factory=dict)


def load_icp_context(business_key: str) -> IcpContext:
    """Best-effort load of positioning + ICP canvases for a brand slug."""
    ctx = IcpContext(brand=business_key)
    candidates = [
        STUDIO_ROOT / ".research" / "positioning" / f"{business_key}.md",
        STUDIO_ROOT / "frameworks" / "positioning-canvas.md",
        STUDIO_ROOT / "frameworks" / "icp-canvas.md",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")[:4000]
        except OSError:
            continue
        ctx.source_files.append(str(path.relative_to(REPO_ROOT)))
        if "icp" in path.name:
            ctx.icp_summary = text[:1200]
        else:
            ctx.positioning = text[:1200]
    return ctx


def _count_matches(text: str, patterns: list[str]) -> int:
    lower = text.lower()
    return sum(1 for p in patterns if re.search(p, lower))


def score_eeat(content: str, *, ymyl: bool = False) -> dict[str, Any]:
    """Heuristic E-E-A-T scores (0–100 per lens)."""
    experience = min(100, 20 + _count_matches(content, [
        r"\b(case study|measured|tested|field|on-site|restor)\w*",
        r"\b\d+%\b",
        r"\b(iicrc|iso|standard)\b",
    ]) * 15)
    expertise = min(100, 15 + _count_matches(content, [
        r"\b(certified|licensed|qualified|years?\s+of\s+experience)\b",
        r"\b(author|by\s+[A-Z][a-z]+)",
    ]) * 20)
    authority = min(100, 10 + _count_matches(content, [
        r"https?://",
        r"\b(research|study|report|standard)\b",
    ]) * 15)
    trust = min(100, 25 + _count_matches(content, [
        r"\b(abn|contact|privacy|terms)\b",
        r"\b(according to|source:|cited)\b",
    ]) * 12)
    scores = {
        "experience": experience,
        "expertise": expertise,
        "authoritativeness": authority,
        "trust": trust,
    }
    if ymyl and trust < 50:
        verdict = "fail"
    elif min(scores.values()) < 40:
        verdict = "needs-work"
    else:
        verdict = "pass"
    return {"scores": scores, "verdict": verdict, "ymyl": ymyl}


def score_geo(content: str) -> dict[str, Any]:
    """Heuristic GEO/AEO extractability score."""
    words = content.split()
    word_count = len(words)
    has_faq = bool(re.search(r"(?m)^#{1,3}\s+.*\?", content) or "?" in content[:400])
    front_loaded = len(words[:200]) >= 40
    has_stat = bool(re.search(r"\b\d+(\.\d+)?%?\b", content[:500]))
    h2_chunks = len(re.findall(r"(?m)^#{2}\s+", content))
    score = 0
    if front_loaded:
        score += 30
    if has_faq:
        score += 25
    if has_stat:
        score += 20
    if h2_chunks >= 1:
        score += 15
    if 80 <= word_count <= 800:
        score += 10
    verdict = "pass" if score >= 60 else "needs-work" if score >= 40 else "fail"
    return {
        "score": min(100, score),
        "verdict": verdict,
        "signals": {
            "front_loaded_answer": front_loaded,
            "faq_or_question": has_faq,
            "concrete_stat": has_stat,
            "h2_sections": h2_chunks,
            "word_count": word_count,
        },
    }


def generate_social_post(
    *,
    business_key: str,
    topic: str,
    body: str,
    channel: str = "linkedin",
    icp: IcpContext | None = None,
) -> GeneratedPost:
    """Build a publisher-ready post with eeat/geo scores."""
    icp = icp or load_icp_context(business_key)
    ymyl = business_key in {"restoreassist", "disaster-recovery", "carsi", "nrpg"}
    preamble = ""
    if icp.positioning:
        preamble = f"{icp.positioning.splitlines()[0].strip()}\n\n"
    content = (preamble + body).strip()
    eeat = score_eeat(content, ymyl=ymyl)
    geo = score_geo(content)
    composite = (
        sum(eeat["scores"].values()) / 4 * 0.55
        + geo["score"] * 0.45
    )
    verdict = "fail" if eeat["verdict"] == "fail" or geo["verdict"] == "fail" else (
        "needs-work" if eeat["verdict"] == "needs-work" or geo["verdict"] == "needs-work"
        else "pass"
    )
    platform_map = {
        "linkedin": ["linkedin"],
        "x": ["x"],
        "twitter": ["x"],
        "instagram": ["instagram"],
        "tiktok": ["tiktok"],
    }
    platforms = platform_map.get(channel.lower(), ["linkedin"])
    hashtags = re.findall(r"#\w+", content)
    return GeneratedPost(
        business_key=business_key,
        content=content,
        title=topic[:120] if topic else f"{business_key} — {channel}",
        platforms=platforms,
        hashtags=hashtags,
        scores=QualityScores(eeat=eeat, geo=geo, composite=round(composite, 1), verdict=verdict),
        metadata={
            "channel": channel,
            "icp_sources": icp.source_files,
            "generator": "marketing_content_generator",
        },
    )


__all__ = [
    "GeneratedPost",
    "IcpContext",
    "QualityScores",
    "generate_social_post",
    "load_icp_context",
    "score_eeat",
    "score_geo",
]
