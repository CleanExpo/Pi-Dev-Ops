#!/usr/bin/env python3
"""Discover external AI capabilities and write portfolio-relevant findings to Brain-1.

The scout watches public creator/research ecosystems, scores discoveries against
the Pi-CEO project registry, and emits a second-brain report plus raw source
notes. It is intentionally read-only toward external systems and does not file
Linear tickets; production adoption remains a human-approved follow-up.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import json
import re
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_JSON = REPO_ROOT / ".harness" / "projects.json"
DEFAULT_BRAIN_ROOT = Path.home() / "2nd-brain"
DEFAULT_LIMIT = 40

SOURCE_PATTERNS = {
    "github": [
        "agent framework",
        "mcp server",
        "ai agent workflow",
        "rag evaluation",
        "autonomous coding agent",
    ],
    "huggingface": [
        "agent",
        "rag",
        "tool-use",
        "code",
        "multimodal",
    ],
    "arxiv": [
        "agentic AI",
        "retrieval augmented generation",
        "multi agent systems",
        "code generation agents",
    ],
}

CAPABILITY_KEYWORDS = {
    "agent_runtime": ["agent", "workflow", "orchestr", "planner", "tool use"],
    "rag_memory": ["rag", "retrieval", "memory", "knowledge", "embedding"],
    "evals": ["eval", "benchmark", "judge", "verification", "safety"],
    "code_automation": ["coding", "code generation", "developer", "software"],
    "multimodal": ["vision", "video", "audio", "multimodal", "voice"],
    "mcp_connector": ["mcp", "model context protocol", "connector"],
    "data_platform": ["supabase", "postgres", "database", "warehouse"],
}

PROJECT_HINTS = {
    "pi-dev-ops": ["agent", "autonomous", "coding", "eval", "workflow", "mcp", "orchestr"],
    "restoreassist": ["insurance", "claim", "restoration", "compliance", "document", "field"],
    "disaster-recovery": ["disaster", "restoration", "seo", "lead", "content", "local"],
    "dr-nrpg": ["contractor", "network", "training", "onboarding", "compliance"],
    "nrpg-onboarding": ["training", "onboarding", "course", "contractor"],
    "synthex": ["content", "brand", "social", "seo", "marketing", "persona"],
    "unite-group": ["crm", "dashboard", "portfolio", "operations", "analytics"],
    "ccw-crm": ["crm", "customer", "quote", "workflow", "service", "field"],
    "carsi": ["compliance", "course", "training", "safety", "audit"],
}


@dataclass(frozen=True)
class ProjectProfile:
    project_id: str
    repo: str
    stack: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Discovery:
    title: str
    url: str
    source_type: str
    summary: str = ""
    published: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityCandidate:
    title: str
    source_url: str
    source_type: str
    summary: str
    project_matches: tuple[str, ...]
    capability_type: str
    maturity: str
    implementation_effort: str
    expected_leverage: str
    risk: str
    recommended_action: str
    relevance_score: int
    discovered_at: str


@dataclass(frozen=True)
class CrmTaskProposal:
    title: str
    description: str
    status: str
    priority: str
    assignee_name: str
    tags: tuple[str, ...]
    obsidian_path: str
    source_url: str
    project_matches: tuple[str, ...]
    capability_type: str
    relevance_score: int
    hermes_lane: str


def slugify(text: str, *, max_len: int = 96) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "untitled"


def load_project_profiles(projects_path: Path = PROJECTS_JSON) -> list[ProjectProfile]:
    data = json.loads(projects_path.read_text(encoding="utf-8"))
    profiles: list[ProjectProfile] = []
    for project in data.get("projects", []):
        project_id = str(project.get("id", "")).strip()
        if not project_id:
            continue
        stack = tuple(str(s).lower() for s in project.get("stack", []) if s)
        keywords = set(PROJECT_HINTS.get(project_id, []))
        keywords.update(project_id.replace("-", " ").split())
        keywords.update(stack)
        if project.get("linear_project_name"):
            keywords.update(str(project["linear_project_name"]).lower().split())
        profiles.append(ProjectProfile(
            project_id=project_id,
            repo=str(project.get("repo", "")),
            stack=tuple(str(s) for s in project.get("stack", []) if s),
            keywords=tuple(sorted(k for k in keywords if len(k) > 2)),
        ))
    return profiles


def _request_json(url: str, *, timeout: int = 20) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Pi-CEO-Capability-Scout/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _request_text(url: str, *, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Pi-CEO-Capability-Scout/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_github_discoveries(limit: int = 12) -> list[Discovery]:
    gh_rows = fetch_github_discoveries_with_cli(limit)
    if gh_rows:
        return gh_rows

    discoveries: list[Discovery] = []
    per_query = max(1, limit // len(SOURCE_PATTERNS["github"]))
    for query in SOURCE_PATTERNS["github"]:
        q = f"{query} stars:>100 pushed:>2026-01-01"
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
            "q": q,
            "sort": "updated",
            "order": "desc",
            "per_page": str(per_query),
        })
        try:
            data = _request_json(url)
        except Exception:
            continue
        for item in (data or {}).get("items", []):  # type: ignore[union-attr]
            discoveries.append(Discovery(
                title=str(item.get("full_name") or item.get("name") or "GitHub repository"),
                url=str(item.get("html_url") or ""),
                source_type="github",
                summary=str(item.get("description") or ""),
                published=str(item.get("updated_at") or "")[:10],
                metadata={
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language") or "",
                },
            ))
    return dedupe_discoveries(discoveries)[:limit]


def fetch_github_discoveries_with_cli(limit: int = 12) -> list[Discovery]:
    discoveries: list[Discovery] = []
    per_query = max(1, limit // len(SOURCE_PATTERNS["github"]))
    for query in SOURCE_PATTERNS["github"]:
        try:
            proc = subprocess.run(
                [
                    "gh", "search", "repos", query,
                    "--limit", str(per_query),
                    "--json", "fullName,url,description,stargazersCount,updatedAt,language",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []
        try:
            rows = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            return []
        for item in rows:
            discoveries.append(Discovery(
                title=str(item.get("fullName") or "GitHub repository"),
                url=str(item.get("url") or ""),
                source_type="github",
                summary=str(item.get("description") or ""),
                published=str(item.get("updatedAt") or "")[:10],
                metadata={
                    "stars": item.get("stargazersCount", 0),
                    "language": item.get("language") or "",
                },
            ))
    return dedupe_discoveries(discoveries)[:limit]


def fetch_huggingface_discoveries(limit: int = 12) -> list[Discovery]:
    discoveries: list[Discovery] = []
    per_query = max(1, limit // len(SOURCE_PATTERNS["huggingface"]))
    for query in SOURCE_PATTERNS["huggingface"]:
        url = "https://huggingface.co/api/models?" + urllib.parse.urlencode({
            "search": query,
            "sort": "lastModified",
            "direction": "-1",
            "limit": str(per_query),
        })
        try:
            data = _request_json(url)
        except Exception:
            continue
        for item in data if isinstance(data, list) else []:
            model_id = str(item.get("modelId") or item.get("id") or "")
            if not model_id:
                continue
            tags = [str(t) for t in item.get("tags", [])[:8]]
            discoveries.append(Discovery(
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                source_type="huggingface",
                summary=", ".join(tags),
                published=str(item.get("lastModified") or "")[:10],
                metadata={
                    "downloads": item.get("downloads", 0),
                    "likes": item.get("likes", 0),
                    "tags": tags,
                },
            ))
    return dedupe_discoveries(discoveries)[:limit]


def fetch_arxiv_discoveries(limit: int = 12) -> list[Discovery]:
    query = " OR ".join(f'all:"{q}"' for q in SOURCE_PATTERNS["arxiv"])
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": query,
        "start": "0",
        "max_results": str(limit),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    try:
        text = _request_text(url)
    except Exception:
        return []
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    out: list[Discovery] = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        link = ""
        for link_el in entry.findall("atom:link", ns):
            if link_el.attrib.get("rel") == "alternate":
                link = link_el.attrib.get("href", "")
                break
        published = (entry.findtext("atom:published", default="", namespaces=ns) or "")[:10]
        if title and link:
            out.append(Discovery(
                title=title,
                url=link,
                source_type="arxiv",
                summary=summary[:700],
                published=published,
            ))
    return out[:limit]


def dedupe_discoveries(discoveries: Iterable[Discovery]) -> list[Discovery]:
    seen: set[str] = set()
    out: list[Discovery] = []
    for item in discoveries:
        key = item.url or item.title.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def classify_capability(text: str) -> str:
    lower = text.lower()
    best = ("general_ai_capability", 0)
    for label, terms in CAPABILITY_KEYWORDS.items():
        hits = sum(1 for term in terms if term in lower)
        if hits > best[1]:
            best = (label, hits)
    return best[0]


def score_discovery(discovery: Discovery, profiles: list[ProjectProfile], *, today: str | None = None) -> CapabilityCandidate | None:
    text = f"{discovery.title} {discovery.summary}".lower()
    matched: list[str] = []
    score = 0
    for profile in profiles:
        hits = sum(1 for keyword in profile.keywords if keyword in text)
        if hits:
            matched.append(profile.project_id)
            score += min(25, hits * 5)

    capability_type = classify_capability(text)
    if capability_type != "general_ai_capability":
        score += 18

    if discovery.source_type == "github":
        stars = int(discovery.metadata.get("stars", 0) or 0)
        if stars >= 1000:
            score += 18
        elif stars >= 100:
            score += 10
        if capability_type in {"agent_runtime", "evals", "mcp_connector", "code_automation"}:
            score += 20
    elif discovery.source_type == "huggingface":
        likes = int(discovery.metadata.get("likes", 0) or 0)
        downloads = int(discovery.metadata.get("downloads", 0) or 0)
        if likes >= 100 or downloads >= 10000:
            score += 14
        elif likes >= 20 or downloads >= 1000:
            score += 8
    elif discovery.source_type == "arxiv":
        score += 8

    if not matched and score < 30:
        return None

    score = max(0, min(100, score))
    maturity = infer_maturity(discovery, score)
    recommended_action = recommended_action_for(score, maturity)
    return CapabilityCandidate(
        title=discovery.title,
        source_url=discovery.url,
        source_type=discovery.source_type,
        summary=discovery.summary.strip(),
        project_matches=tuple(matched[:5] or ("pi-dev-ops",)),
        capability_type=capability_type,
        maturity=maturity,
        implementation_effort=infer_effort(capability_type),
        expected_leverage=infer_leverage(score),
        risk=infer_risk(discovery, maturity),
        recommended_action=recommended_action,
        relevance_score=score,
        discovered_at=today or dt.date.today().isoformat(),
    )


def infer_maturity(discovery: Discovery, score: int) -> str:
    if discovery.source_type == "github":
        stars = int(discovery.metadata.get("stars", 0) or 0)
        if stars >= 1000:
            return "adoptable"
        if stars >= 100:
            return "sandbox"
        return "watch"
    if discovery.source_type == "huggingface":
        likes = int(discovery.metadata.get("likes", 0) or 0)
        downloads = int(discovery.metadata.get("downloads", 0) or 0)
        if likes >= 100 or downloads >= 10000:
            return "sandbox"
        return "watch"
    if discovery.source_type == "arxiv":
        return "research"
    return "watch" if score < 75 else "sandbox"


def infer_effort(capability_type: str) -> str:
    if capability_type in {"mcp_connector", "rag_memory", "evals"}:
        return "1-3 days spike"
    if capability_type in {"agent_runtime", "code_automation"}:
        return "3-7 days sandbox"
    return "half-day review"


def infer_leverage(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def infer_risk(discovery: Discovery, maturity: str) -> str:
    if discovery.source_type == "arxiv":
        return "research-only until independently reproduced"
    if maturity == "adoptable":
        return "dependency and security review required"
    return "immature signal; keep out of production"


def recommended_action_for(score: int, maturity: str) -> str:
    if score >= 80 and maturity in {"adoptable", "sandbox"}:
        return "create sandbox spike and draft skill candidate"
    if score >= 70:
        return "write Brain-1 synthesis and queue for human review"
    if score >= 50:
        return "watchlist"
    return "ignore unless repeated by future scans"


def crm_priority_for(candidate: CapabilityCandidate) -> str:
    if candidate.relevance_score >= 80:
        return "high"
    if candidate.relevance_score >= 60:
        return "medium"
    return "low"


def hermes_lane_for(candidate: CapabilityCandidate) -> str:
    if candidate.capability_type in {"agent_runtime", "code_automation", "mcp_connector"}:
        return "engineering"
    if candidate.capability_type in {"rag_memory", "evals", "data_platform"}:
        return "research-ops"
    if candidate.capability_type == "multimodal":
        return "content-systems"
    return "watchlist"


def candidate_obsidian_path(candidate: CapabilityCandidate) -> str:
    return f"Sources/{candidate.discovered_at}-capability-{slugify(candidate.title)}.md"


def candidate_to_crm_task(candidate: CapabilityCandidate) -> CrmTaskProposal:
    obsidian_path = candidate_obsidian_path(candidate)
    tags = (
        "capability-scout",
        "approval-required",
        "unite-crm",
        "second-brain",
        "hermes-intake",
        candidate.capability_type,
        candidate.source_type,
    )
    description = "\n".join([
        f"Review external AI capability: {candidate.title}",
        "",
        f"Source: {candidate.source_url}",
        f"Second brain note: {obsidian_path}",
        f"Matched projects: {', '.join(candidate.project_matches)}",
        f"Capability type: {candidate.capability_type}",
        f"Relevance score: {candidate.relevance_score}",
        f"Maturity: {candidate.maturity}",
        f"Expected leverage: {candidate.expected_leverage}",
        f"Implementation effort: {candidate.implementation_effort}",
        f"Risk: {candidate.risk}",
        f"Recommended action: {candidate.recommended_action}",
        f"Hermes lane: {hermes_lane_for(candidate)}",
        "",
        "Safety gates:",
        "- This is an intake proposal, not permission to install or ship.",
        "- CRM remains the operational source of truth once a human approves the task.",
        "- Obsidian remains the knowledge source and evidence trail.",
        "- Hermes may prepare research or sandbox plans, but production changes need human approval.",
    ])
    return CrmTaskProposal(
        title=f"Review capability: {candidate.title[:90]}",
        description=description,
        status="blocked",
        priority=crm_priority_for(candidate),
        assignee_name="Phill approval",
        tags=tags,
        obsidian_path=obsidian_path,
        source_url=candidate.source_url,
        project_matches=candidate.project_matches,
        capability_type=candidate.capability_type,
        relevance_score=candidate.relevance_score,
        hermes_lane=hermes_lane_for(candidate),
    )


def build_candidates(discoveries: Iterable[Discovery], profiles: list[ProjectProfile], *, today: str | None = None) -> list[CapabilityCandidate]:
    candidates = [
        candidate
        for discovery in dedupe_discoveries(discoveries)
        if (candidate := score_discovery(discovery, profiles, today=today)) is not None
    ]
    return sorted(candidates, key=lambda c: c.relevance_score, reverse=True)


def candidate_to_markdown(candidate: CapabilityCandidate) -> str:
    return textwrap.dedent(f"""\
    ---
    type: capability-source
    source_type: {candidate.source_type}
    capability_type: {candidate.capability_type}
    relevance_score: {candidate.relevance_score}
    maturity: {candidate.maturity}
    status: proposed
    crm_status: intake-ready
    obsidian_path: "{candidate_obsidian_path(candidate)}"
    hermes_lane: {hermes_lane_for(candidate)}
    discovered: {candidate.discovered_at}
    source: "{candidate.source_url}"
    projects: [{", ".join(candidate.project_matches)}]
    ---

    # {candidate.title}

    {candidate.summary or "No summary provided by source feed."}

    - Source: {candidate.source_url}
    - Matched projects: {", ".join(candidate.project_matches)}
    - Capability type: {candidate.capability_type}
    - Expected leverage: {candidate.expected_leverage}
    - Effort: {candidate.implementation_effort}
    - Risk: {candidate.risk}
    - Recommended action: {candidate.recommended_action}
    - CRM intake: blocked approval task proposal
    - Hermes lane: {hermes_lane_for(candidate)}
    """)


def render_report(candidates: list[CapabilityCandidate], *, today: str | None = None) -> str:
    day = today or dt.date.today().isoformat()
    lines = [
        "---",
        "type: capability-scout-report",
        f"date: {day}",
        f"candidate_count: {len(candidates)}",
        "---",
        "",
        f"# Capability Scout Report — {day}",
        "",
        "External AI capability discoveries mapped against the Pi-CEO project registry.",
        "",
        "## Top Candidates",
        "",
    ]
    if not candidates:
        lines.append("No relevant candidates found.")
    for candidate in candidates[:15]:
        lines.extend([
            f"### {candidate.title}",
            "",
            f"- Score: {candidate.relevance_score}",
            f"- Source: [{candidate.source_type}]({candidate.source_url})",
            f"- Projects: {', '.join(candidate.project_matches)}",
            f"- Capability: {candidate.capability_type}",
            f"- Maturity: {candidate.maturity}",
            f"- Leverage: {candidate.expected_leverage}",
            f"- Action: {candidate.recommended_action}",
            f"- Risk: {candidate.risk}",
            "",
            candidate.summary[:700] if candidate.summary else "_No source summary available._",
            "",
        ])
    lines.extend([
        "## Operating Notes",
        "",
        "- This report is discovery intelligence, not approval to install or ship dependencies.",
        "- Production adoption still needs sandbox validation, security review, and human approval.",
        "- High-scoring repeated signals should become skill candidates or project DoD proposals.",
        "- CRM intake payloads use `obsidian_path` as the join key between Unite-Group CRM, Hermes, and Brain-1.",
        "",
    ])
    return "\n".join(lines)


def write_crm_bridge(candidates: list[CapabilityCandidate], outcomes_dir: Path, *, day: str) -> Path:
    bridge_path = outcomes_dir / f"{day}-capability-crm-intake.jsonl"
    with bridge_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            proposal = candidate_to_crm_task(candidate)
            handle.write(json.dumps(proposal.__dict__, sort_keys=True) + "\n")
    return bridge_path


def write_brain_outputs(candidates: list[CapabilityCandidate], brain_root: Path = DEFAULT_BRAIN_ROOT, *, today: str | None = None) -> dict[str, object]:
    day = today or dt.date.today().isoformat()
    outcomes_dir = brain_root / "Outcomes" / "capability-scout"
    sources_dir = brain_root / "Sources"
    outcomes_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    report_path = outcomes_dir / f"{day}-capability-scout.md"
    report_path.write_text(render_report(candidates, today=day), encoding="utf-8")

    source_paths: list[str] = []
    for candidate in candidates[:20]:
        source_path = brain_root / candidate_obsidian_path(candidate)
        source_path.write_text(candidate_to_markdown(candidate), encoding="utf-8")
        source_paths.append(str(source_path))

    crm_bridge_path = write_crm_bridge(candidates[:20], outcomes_dir, day=day)
    crm_tasks = [candidate_to_crm_task(candidate).__dict__ for candidate in candidates[:20]]
    manifest_path = outcomes_dir / f"{day}-capability-scout.json"
    manifest = {
        "date": day,
        "candidate_count": len(candidates),
        "report_path": str(report_path),
        "source_paths": source_paths,
        "crm_bridge_path": str(crm_bridge_path),
        "crm_tasks": crm_tasks,
        "operating_bridge": {
            "obsidian": "knowledge substrate and evidence trail",
            "unite_group_crm": "human-approved operational queue",
            "hermes": "research and sandbox execution lane",
            "join_key": "obsidian_path",
        },
        "candidates": [candidate.__dict__ for candidate in candidates],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "crm_bridge_path": str(crm_bridge_path),
        "source_count": len(source_paths),
        "crm_task_count": len(crm_tasks),
    }


def fetch_live_discoveries(limit: int) -> list[Discovery]:
    per_source = max(3, limit // 3)
    discoveries: list[Discovery] = []
    discoveries.extend(fetch_github_discoveries(per_source))
    discoveries.extend(fetch_huggingface_discoveries(per_source))
    discoveries.extend(fetch_arxiv_discoveries(per_source))
    return dedupe_discoveries(discoveries)[:limit]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scout external AI capabilities for Pi-CEO projects.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum raw discoveries to fetch.")
    parser.add_argument("--min-score", type=int, default=45, help="Minimum relevance score to include.")
    parser.add_argument("--brain-root", type=Path, default=DEFAULT_BRAIN_ROOT, help="Path to active Obsidian/Brain-1 vault.")
    parser.add_argument("--projects", type=Path, default=PROJECTS_JSON, help="Path to .harness/projects.json.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write Brain-1 files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    profiles = load_project_profiles(args.projects)
    discoveries = fetch_live_discoveries(args.limit)
    candidates = [
        c for c in build_candidates(discoveries, profiles)
        if c.relevance_score >= args.min_score
    ]

    result: dict[str, object] = {
        "discoveries": len(discoveries),
        "candidates": len(candidates),
        "top": [c.__dict__ for c in candidates[:5]],
    }
    if not args.dry_run:
        result["brain"] = write_brain_outputs(candidates, args.brain_root)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Capability Scout: {len(discoveries)} discoveries, {len(candidates)} candidates")
        for c in candidates[:5]:
            print(f"- {c.relevance_score:3d} {c.title} -> {', '.join(c.project_matches)}")
        if result.get("brain"):
            brain = result["brain"]
            print(f"Report: {brain['report_path']}")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
