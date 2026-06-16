#!/usr/bin/env python3
"""Expand a raw operator idea into research and execution packets.

This is the strategic augmentation layer: it prevents the system from treating
operator input as only a literal build instruction. A short idea becomes an
opportunity map, research lanes, implementation options, risk notes, durable
2nd-brain artifacts, and CRM-ready approval proposals.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import capability_crm_import
from scripts.capability_scout import DEFAULT_BRAIN_ROOT, slugify


STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "before",
    "build",
    "could",
    "for",
    "from",
    "have",
    "into",
    "just",
    "make",
    "more",
    "need",
    "should",
    "that",
    "the",
    "this",
    "too",
    "with",
    "what",
    "when",
    "where",
    "will",
    "your",
}

RESEARCH_TEMPLATES = [
    (
        "github",
        "Find open-source implementations, agent workflows, MCP servers, and "
        "product patterns related to {topic}.",
    ),
    (
        "huggingface",
        "Find models, datasets, demos, and Spaces that could extend {topic}.",
    ),
    (
        "papers",
        "Find recent papers on agentic systems, evaluation, retrieval, human "
        "approval, and workflow automation for {topic}.",
    ),
    (
        "products",
        "Compare commercial product patterns, UI decisions, and operating models "
        "around {topic}.",
    ),
    (
        "security",
        "Identify safety, approval, data-boundary, and operational risk patterns "
        "for {topic}.",
    ),
    (
        "implementation",
        "Find architecture patterns and integration approaches for turning "
        "{topic} into a production workflow.",
    ),
]


@dataclass(frozen=True)
class ResearchLane:
    lane: str
    question: str
    queries: tuple[str, ...]
    expected_output: str


@dataclass(frozen=True)
class IdeaExpansion:
    raw_idea: str
    title: str
    slug: str
    generated_at: str
    keywords: tuple[str, ...]
    direct_ask: str
    strategic_read: str
    adjacent_opportunities: tuple[str, ...]
    second_order_effects: tuple[str, ...]
    research_lanes: tuple[ResearchLane, ...]
    implementation_candidates: tuple[str, ...]
    risks: tuple[str, ...]
    crm_tasks: tuple[dict[str, Any], ...]


def keywords_for(idea: str, *, limit: int = 8) -> tuple[str, ...]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", idea.lower())
    out: list[str] = []
    for token in tokens:
        if token in STOPWORDS or token in out:
            continue
        out.append(token)
    return tuple(out[:limit] or ("idea",))


def title_for(idea: str) -> str:
    cleaned = " ".join(idea.strip().split())
    if not cleaned:
        return "Untitled Strategic Expansion"
    if len(cleaned) <= 90:
        return cleaned.rstrip(" .,")
    return (cleaned[:90].rsplit(" ", 1)[0] or cleaned[:90]).rstrip(" .,")


def phrase(keywords: tuple[str, ...]) -> str:
    return " ".join(keywords[:4])


def build_research_lanes(title: str, keywords: tuple[str, ...]) -> tuple[ResearchLane, ...]:
    topic = phrase(keywords)
    lanes: list[ResearchLane] = []
    for lane, question in RESEARCH_TEMPLATES:
        base = question.format(topic=title)
        queries = (
            f"{topic} {lane} AI agent",
            f"{title} workflow automation",
            f"{topic} approval governance implementation",
        )
        lanes.append(ResearchLane(
            lane=lane,
            question=base,
            queries=queries,
            expected_output=f"Sourced findings that improve, challenge, or de-risk {title}.",
        ))
    return tuple(lanes)


def build_crm_task(
    *,
    title: str,
    description: str,
    priority: str,
    obsidian_path: str,
    source_url: str,
    capability_type: str,
    hermes_lane: str,
    relevance_score: int,
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "status": "blocked",
        "priority": priority,
        "assignee_name": "Phill approval",
        "tags": [
            "capability-scout",
            "idea-expansion",
            "strategic-expansion",
            "approval-required",
            "unite-crm",
            "second-brain",
            "hermes-intake",
            capability_type,
        ],
        "obsidian_path": obsidian_path,
        "source_url": source_url,
        "project_matches": ["pi-dev-ops", "unite-group"],
        "capability_type": capability_type,
        "relevance_score": relevance_score,
        "hermes_lane": hermes_lane,
    }


def expand_idea(idea: str, *, today: str | None = None) -> IdeaExpansion:
    day = today or dt.date.today().isoformat()
    title = title_for(idea)
    slug = slugify(title)
    keywords = keywords_for(idea)
    research_lanes = build_research_lanes(title, keywords)
    decision_path = f"Outcomes/idea-expansion/{day}-{slug}-decision-brief.md"
    source_url = f"obsidian://idea-expansion/{day}-{slug}"

    adjacent = (
        "Turn the literal request into an approval-gated operating workflow.",
        "Create research lanes that compare external products, repos, papers, "
        "and implementation patterns.",
        "Generate CRM follow-up tasks so the idea can move through human "
        "approval instead of disappearing into notes.",
        "Convert repeated or high-leverage findings into reusable skills, "
        "not one-off implementation memory.",
        "Feed outcomes back into scoring so future expansions learn from "
        "approved, rejected, and failed ideas.",
    )
    second_order = (
        "The system becomes an augmenter: it proposes adjacent leverage before "
        "implementing narrow surface work.",
        "Research becomes a default continuation step, not a separate prompt "
        "the operator must remember to ask for.",
        "2nd-brain artifacts become reusable context for future agents, Hermes "
        "lanes, and CRM approvals.",
        "Approval gating keeps the system from auto-installing or shipping "
        "immature external capabilities.",
    )
    implementation = (
        "Add idea expansion as a script/API callable from operator chat, "
        "command-center, and cron-triggered reviews.",
        "Write expansion packets to the 2nd brain with stable paths and CRM bridge JSONL.",
        "Route research tasks to Hermes by lane before any sandbox or production work begins.",
        "Add read-back validation that proves idea note, research note, "
        "decision brief, and CRM proposal all exist.",
    )
    risks = (
        "Expansion can overreach if it treats every idea as permission to build adjacent systems.",
        "Research quality can drift if generated queries are too generic.",
        "CRM queues can become noisy unless low-confidence ideas are watchlisted "
        "instead of actioned.",
        "External tools must remain sandbox-only until reviewed for license, "
        "security, maintenance, and fit.",
    )

    crm_tasks = (
        build_crm_task(
            title=f"Research expansion: {title[:70]}",
            description=(
                f"Research the wider opportunity space around: {title}\n\n"
                f"Decision brief: {decision_path}\n"
                "Outcome required: sourced findings, options, risks, and a recommendation."
            ),
            priority="high",
            obsidian_path=decision_path,
            source_url=source_url,
            capability_type="rag_memory",
            hermes_lane="research-ops",
            relevance_score=82,
        ),
        build_crm_task(
            title=f"Approve sandbox plan: {title[:68]}",
            description=(
                f"Review the safe implementation/sandbox plan for: {title}\n\n"
                "No production write, install, vendor onboarding, or external "
                "account action is allowed from this task alone."
            ),
            priority="high",
            obsidian_path=decision_path,
            source_url=source_url,
            capability_type="agent_runtime",
            hermes_lane="engineering",
            relevance_score=78,
        ),
        build_crm_task(
            title=f"Consider skill candidate: {title[:68]}",
            description=(
                f"Decide whether this idea should become a reusable SKILL.md candidate: {title}\n\n"
                "Only approve if the workflow is repeated, bounded, testable, and safe to trigger."
            ),
            priority="medium",
            obsidian_path=decision_path,
            source_url=source_url,
            capability_type="agent_runtime",
            hermes_lane="engineering",
            relevance_score=70,
        ),
    )

    capability_crm_import.validate_proposals(list(crm_tasks))
    return IdeaExpansion(
        raw_idea=idea,
        title=title,
        slug=slug,
        generated_at=day,
        keywords=keywords,
        direct_ask=f"Implement or address the operator's stated idea: {title}.",
        strategic_read=(
            "Treat the idea as a signal for a wider capability. Expand adjacent workflows, "
            "research external examples, identify leverage/risk, then return an operating packet."
        ),
        adjacent_opportunities=adjacent,
        second_order_effects=second_order,
        research_lanes=research_lanes,
        implementation_candidates=implementation,
        risks=risks,
        crm_tasks=crm_tasks,
    )


def lane_to_dict(lane: ResearchLane) -> dict[str, Any]:
    return {
        "lane": lane.lane,
        "question": lane.question,
        "queries": list(lane.queries),
        "expected_output": lane.expected_output,
    }


def expansion_to_dict(expansion: IdeaExpansion) -> dict[str, Any]:
    return {
        "raw_idea": expansion.raw_idea,
        "title": expansion.title,
        "slug": expansion.slug,
        "generated_at": expansion.generated_at,
        "keywords": list(expansion.keywords),
        "direct_ask": expansion.direct_ask,
        "strategic_read": expansion.strategic_read,
        "adjacent_opportunities": list(expansion.adjacent_opportunities),
        "second_order_effects": list(expansion.second_order_effects),
        "research_lanes": [lane_to_dict(lane) for lane in expansion.research_lanes],
        "implementation_candidates": list(expansion.implementation_candidates),
        "risks": list(expansion.risks),
        "crm_tasks": list(expansion.crm_tasks),
    }


def render_idea_note(expansion: IdeaExpansion) -> str:
    return textwrap.dedent(f"""\
    ---
    type: idea-expansion
    status: expanded
    date: {expansion.generated_at}
    slug: {expansion.slug}
    ---

    # {expansion.title}

    ## Raw Idea

    {expansion.raw_idea}

    ## Direct Ask

    {expansion.direct_ask}

    ## Strategic Read

    {expansion.strategic_read}

    ## Adjacent Opportunities

    {chr(10).join(f"- {item}" for item in expansion.adjacent_opportunities)}

    ## Second-Order Effects

    {chr(10).join(f"- {item}" for item in expansion.second_order_effects)}
    """)


def render_research_note(expansion: IdeaExpansion) -> str:
    lines = [
        "---",
        "type: idea-research-lanes",
        f"date: {expansion.generated_at}",
        f"idea: {expansion.slug}",
        "---",
        "",
        f"# Research Lanes - {expansion.title}",
        "",
    ]
    for lane in expansion.research_lanes:
        lines.extend([
            f"## {lane.lane}",
            "",
            lane.question,
            "",
            "Queries:",
            *[f"- {query}" for query in lane.queries],
            "",
            f"Expected output: {lane.expected_output}",
            "",
        ])
    return "\n".join(lines)


def render_decision_brief(expansion: IdeaExpansion) -> str:
    crm_queue = "\n".join(
        f"- {task['title']} ({task['priority']}, {task['hermes_lane']})"
        for task in expansion.crm_tasks
    )
    return textwrap.dedent(f"""\
    ---
    type: idea-decision-brief
    status: approval-required
    date: {expansion.generated_at}
    idea: {expansion.slug}
    crm_task_count: {len(expansion.crm_tasks)}
    ---

    # Decision Brief - {expansion.title}

    ## Recommendation

    Approve a research spike first. Do not jump directly from the raw idea to
    production implementation.

    ## Implementation Candidates

    {chr(10).join(f"- {item}" for item in expansion.implementation_candidates)}

    ## Risks

    {chr(10).join(f"- {item}" for item in expansion.risks)}

    ## CRM Approval Queue

    {crm_queue}

    ## Safety Boundary

    This packet expands the idea and queues approval tasks. It is not approval to
    install dependencies, create vendor accounts, write production data, or ship
    code without the relevant project gates.
    """)


def write_outputs(
    expansion: IdeaExpansion,
    brain_root: Path = DEFAULT_BRAIN_ROOT,
) -> dict[str, Any]:
    day = expansion.generated_at
    ideas_dir = brain_root / "Ideas"
    research_dir = brain_root / "Research"
    outcomes_dir = brain_root / "Outcomes" / "idea-expansion"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)
    outcomes_dir.mkdir(parents=True, exist_ok=True)

    idea_path = ideas_dir / f"{day}-{expansion.slug}.md"
    research_path = research_dir / f"{day}-{expansion.slug}-research.md"
    decision_path = outcomes_dir / f"{day}-{expansion.slug}-decision-brief.md"
    crm_bridge_path = outcomes_dir / f"{day}-{expansion.slug}-crm-intake.jsonl"
    manifest_path = outcomes_dir / f"{day}-{expansion.slug}.json"

    idea_path.write_text(render_idea_note(expansion), encoding="utf-8")
    research_path.write_text(render_research_note(expansion), encoding="utf-8")
    decision_path.write_text(render_decision_brief(expansion), encoding="utf-8")
    with crm_bridge_path.open("w", encoding="utf-8") as handle:
        for task in expansion.crm_tasks:
            handle.write(json.dumps(task, sort_keys=True) + "\n")

    manifest = expansion_to_dict(expansion)
    manifest.update({
        "idea_path": str(idea_path),
        "research_path": str(research_path),
        "decision_path": str(decision_path),
        "crm_bridge_path": str(crm_bridge_path),
        "crm_task_count": len(expansion.crm_tasks),
    })
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    capability_crm_import.validate_proposals(
        capability_crm_import.load_manifest_or_jsonl(crm_bridge_path),
    )
    return {
        "idea_path": str(idea_path),
        "research_path": str(research_path),
        "decision_path": str(decision_path),
        "manifest_path": str(manifest_path),
        "crm_bridge_path": str(crm_bridge_path),
        "crm_task_count": len(expansion.crm_tasks),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand a raw idea into research, 2nd-brain, and CRM packets.",
    )
    parser.add_argument("idea", nargs="*", help="Raw idea text.")
    parser.add_argument("--idea-file", type=Path, help="Read raw idea text from a file.")
    parser.add_argument("--brain-root", type=Path, default=DEFAULT_BRAIN_ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def idea_from_args(args: argparse.Namespace) -> str:
    if args.idea_file:
        return args.idea_file.read_text(encoding="utf-8").strip()
    return " ".join(args.idea).strip()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    idea = idea_from_args(args)
    if not idea:
        print("Idea expansion failed: empty idea", file=sys.stderr)
        return 1

    expansion = expand_idea(idea)
    result: dict[str, Any] = {
        "ok": True,
        "expansion": expansion_to_dict(expansion),
    }
    if not args.dry_run:
        result["brain"] = write_outputs(expansion, args.brain_root)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Idea expansion: {expansion.title}")
        print(f"- Research lanes: {len(expansion.research_lanes)}")
        print(f"- CRM tasks: {len(expansion.crm_tasks)}")
        if result.get("brain"):
            print(f"Decision brief: {result['brain']['decision_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
