"""
scout.py — Scout Agent: External Intelligence Gathering (RA-684)

Runs weekly to search GitHub, ArXiv, and Hacker News for relevant
AI/LLM/agent tooling intelligence, scores findings against ZTE dimensions,
de-duplicates, and creates Linear issues for the top results.

Usage:
    python -m app.server.agents.scout [--dry-run]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.agents.scout")

_HARNESS = Path(__file__).parent.parent.parent.parent / ".harness"
_SEEN_FILE = _HARNESS / "scout-seen.json"
_RESEARCH_INBOX = _HARNESS / "scout-research-inbox.jsonl"
_MAX_SEEN = 500
_RELEVANCE_THRESHOLD = 2  # findings below this score route to research inbox, not Linear

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"

_ZTE_DIMENSIONS = [
    "spec_quality", "context_precision", "model_selection", "tool_availability",
    "feedback_loops", "error_recovery", "session_continuity", "quality_gating",
    "cost_efficiency", "trigger_automation", "knowledge_retention",
    "workflow_standardisation", "observability", "external_validation", "incident_history",
]
_ZTE_KEYWORDS = {
    "spec_quality": ["specification", "spec", "requirements", "prompt engineering"],
    "context_precision": ["context window", "context length", "rag", "retrieval", "chunking"],
    "model_selection": ["model selection", "routing", "llm comparison", "benchmark", "eval"],
    "tool_availability": ["tool use", "function calling", "mcp", "tool calling", "plugins"],
    "feedback_loops": ["feedback", "rlhf", "reinforcement", "reward", "human in the loop"],
    "error_recovery": ["error recovery", "retry", "fallback", "resilience", "fault tolerance"],
    "session_continuity": ["session", "memory", "long-term", "persistence", "stateful"],
    "quality_gating": ["quality gate", "evaluation", "testing", "validation", "ci/cd"],
    "cost_efficiency": ["cost", "token efficiency", "budget", "latency", "throughput"],
    "trigger_automation": ["automation", "cron", "scheduled", "trigger", "workflow"],
    "knowledge_retention": ["knowledge base", "vector", "embedding", "semantic search"],
    "workflow_standardisation": ["workflow", "orchestration", "pipeline", "agent framework"],
    "observability": ["observability", "tracing", "logging", "monitoring", "telemetry"],
    "external_validation": ["external validation", "red team", "safety", "alignment"],
    "incident_history": ["incident", "post-mortem", "outage", "failure analysis"],
}


# ── Deduplication ─────────────────────────────────────────────────────────────

def _load_seen() -> list[str]:
    try:
        return json.loads(_SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_seen(seen: list[str]) -> None:
    _HARNESS.mkdir(parents=True, exist_ok=True)
    tmp = str(_SEEN_FILE) + ".tmp"
    Path(tmp).write_text(json.dumps(seen, indent=2), encoding="utf-8")
    Path(tmp).replace(_SEEN_FILE)


def _hash_id(url: str, title: str) -> str:
    key = f"{url.strip().lower()}|{title.strip().lower()[:80]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _is_new(item_id: str, seen: list[str]) -> bool:
    return item_id not in seen


def _add_seen(item_id: str, seen: list[str]) -> list[str]:
    seen = [s for s in seen if s != item_id]  # move to end (FIFO tail)
    seen.append(item_id)
    if len(seen) > _MAX_SEEN:
        seen = seen[-_MAX_SEEN:]
    return seen


# ── Relevance scoring ─────────────────────────────────────────────────────────

def _score_finding(title: str, description: str) -> tuple[int, list[str]]:
    """Score 0-5 by matching ZTE dimension keywords. Returns (score, matched_dims)."""
    text = (title + " " + description).lower()
    matched: list[str] = []
    for dim, keywords in _ZTE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(dim)
    return min(len(matched), 5), matched[:5]


# ── Source: GitHub ────────────────────────────────────────────────────────────

def _github_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_github(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page={max_results}"
    try:
        req = urllib.request.Request(url, headers=_github_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        items = data.get("items", [])
        return [
            {
                "source": "github",
                "title": item.get("full_name", ""),
                "url": item.get("html_url", ""),
                "description": item.get("description") or "",
                "stars": item.get("stargazers_count", 0),
            }
            for item in items
        ]
    except Exception as exc:
        log.warning("GitHub fetch failed (query=%r): %s", query, exc)
        return []


def fetch_github_findings() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    results += _fetch_github("topic:llm topic:agent", max_results=10)
    results += _fetch_github("autonomous agent language-model", max_results=10)
    seen_urls: set[str] = set()
    unique: list[dict[str, Any]] = []
    for r in results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique.append(r)
    log.info("GitHub: %d unique repos found", len(unique))
    return unique


# ── Source: ArXiv ─────────────────────────────────────────────────────────────

_ARXIV_NS = "http://www.w3.org/2005/Atom"


def _parse_arxiv_entry(entry: ET.Element) -> dict[str, Any] | None:
    title_el = entry.find(f"{{{_ARXIV_NS}}}title")
    id_el = entry.find(f"{{{_ARXIV_NS}}}id")
    summary_el = entry.find(f"{{{_ARXIV_NS}}}summary")
    if title_el is None or id_el is None:
        return None
    return {
        "source": "arxiv",
        "title": (title_el.text or "").strip(),
        "url": (id_el.text or "").strip(),
        "description": (summary_el.text or "").strip()[:400] if summary_el is not None else "",
    }


def fetch_arxiv_findings() -> list[dict[str, Any]]:
    url = (
        "https://export.arxiv.org/api/query"
        "?search_query=all:agentic+AND+all:llm"
        "&sortBy=submittedDate&maxResults=5"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pi-ceo-scout/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        entries = root.findall(f"{{{_ARXIV_NS}}}entry")
        results = [_parse_arxiv_entry(e) for e in entries]
        findings = [r for r in results if r is not None]
        log.info("ArXiv: %d papers found", len(findings))
        return findings
    except Exception as exc:
        log.warning("ArXiv fetch failed: %s", exc)
        return []


# ── Source: Hacker News ───────────────────────────────────────────────────────

def fetch_hn_findings() -> list[dict[str, Any]]:
    url = (
        "https://hn.algolia.com/api/v1/search"
        "?query=AI+agent+autonomous&tags=story&hitsPerPage=10"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pi-ceo-scout/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        hits = data.get("hits", [])
        findings: list[dict[str, Any]] = []
        for hit in hits:
            score = hit.get("points", 0) or 0
            if score <= 50:
                continue
            obj_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            findings.append({
                "source": "hackernews",
                "title": hit.get("title", ""),
                "url": obj_url,
                "description": hit.get("story_text") or "",
                "score": score,
            })
        log.info("Hacker News: %d stories with score > 50", len(findings))
        return findings
    except Exception as exc:
        log.warning("Hacker News fetch failed: %s", exc)
        return []


# ── Linear integration ────────────────────────────────────────────────────────

def _existing_scout_titles(api_key: str) -> set[str] | None:
    """Fetch titles of open [SCOUT] tickets in the project for dedup.

    Source-of-truth dedup: the local .harness/scout-seen.json cache is per-env,
    so scout running in multiple environments (local, Railway, CCR) accumulates
    duplicates. Querying Linear directly catches dupes regardless of cache state.

    Returns None when the fetch fails so the caller can fail CLOSED (skip
    filing) instead of filing blind. The 2026-06 dupe storm (RA-5663 et al.,
    6 copies each) happened because this query typed the project variable as
    a GraphQL String where Linear's IDComparator expects `ID` — every call
    400'd, the exception was swallowed, and scout filed blind on every cycle.
    """
    query = """
    query OpenScoutIssues($projectId: ID!) {
        issues(
            filter: {
                project: { id: { eq: $projectId } },
                state: { type: { in: ["backlog","unstarted","started"] } },
                title: { startsWith: "[SCOUT]" }
            },
            first: 250
        ) { nodes { title } }
    }
    """
    try:
        payload = json.dumps({"query": query, "variables": {"projectId": _PROJECT_ID}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read()).get("data", {})
        nodes = (data.get("issues") or {}).get("nodes", [])
        return {n["title"].strip().lower() for n in nodes if n.get("title")}
    except Exception as exc:
        log.warning("Scout: existing title fetch failed (%s) — failing closed, "
                    "no issues will be filed this cycle", exc)
        return None


def _get_or_create_scout_label(api_key: str) -> str | None:
    """Try to find or create a 'scout' label. Returns label ID or None."""
    query = """
    query TeamLabels($teamId: String!) {
        team(id: $teamId) { labels { nodes { id name } } }
    }
    """
    try:
        payload = json.dumps({"query": query, "variables": {"teamId": _TEAM_ID}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        labels = (data.get("team") or {}).get("labels", {}).get("nodes", [])
        for lbl in labels:
            if lbl.get("name", "").lower() == "scout":
                return lbl["id"]
    except Exception as exc:
        log.warning("Scout label lookup failed: %s", exc)
        return None

    mutation = """
    mutation CreateLabel($input: IssueLabelCreateInput!) {
        issueLabelCreate(input: $input) { success issueLabel { id } }
    }
    """
    try:
        payload = json.dumps({
            "query": mutation,
            "variables": {"input": {"teamId": _TEAM_ID, "name": "scout", "color": "#6B7FD7"}},
        }).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        return (data.get("issueLabelCreate") or {}).get("issueLabel", {}).get("id")
    except Exception as exc:
        log.warning("Scout label creation failed: %s", exc)
        return None


def _create_linear_issue(finding: dict[str, Any], label_id: str | None, api_key: str) -> str | None:
    """Create a Linear issue for a scout finding. Returns identifier or None."""
    source = finding["source"].upper()
    title_short = finding["title"][:80]
    issue_title = f"[SCOUT] {source}: {title_short}"
    dims_str = ", ".join(finding.get("matched_dims", []))
    description = (
        f"**Source:** {finding['source']}\n"
        f"**URL:** {finding['url']}\n"
        f"**Relevance Score:** {finding['relevance_score']}/5\n"
        f"**Matched ZTE Dimensions:** {dims_str or 'none'}\n\n"
        f"**Summary:** {finding['description'][:300] or '(no description)'}"
    )
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) { success issue { identifier } }
    }
    """
    issue_input: dict[str, Any] = {
        "teamId": _TEAM_ID,
        "projectId": _PROJECT_ID,
        "title": issue_title,
        "description": description,
        "priority": 3,
    }
    if label_id:
        issue_input["labelIds"] = [label_id]
    try:
        payload = json.dumps({"query": mutation, "variables": {"input": issue_input}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        identifier = (data.get("issueCreate") or {}).get("issue", {}).get("identifier")
        log.info("Created Linear issue %s for %s: %s", identifier, finding["source"], title_short)
        return identifier
    except Exception as exc:
        log.warning("Linear issue creation failed for %r: %s", finding["title"], exc)
        return None


# ── RA-6756: Scout deduplication helpers ─────────────────────────────────────

def _get_or_create_cleanup_label(api_key: str) -> str | None:
    """Find or create a 'cleanup' label in the team. Returns label ID or None."""
    query = """
    query TeamLabels($teamId: String!) {
        team(id: $teamId) { labels { nodes { id name } } }
    }
    """
    try:
        payload = json.dumps({"query": query, "variables": {"teamId": _TEAM_ID}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        labels = (data.get("team") or {}).get("labels", {}).get("nodes", [])
        for lbl in labels:
            if lbl.get("name", "").lower() == "cleanup":
                return lbl["id"]
    except Exception as exc:
        log.warning("Cleanup label lookup failed: %s", exc)
        return None
    mutation = """
    mutation CreateLabel($input: IssueLabelCreateInput!) {
        issueLabelCreate(input: $input) { success issueLabel { id } }
    }
    """
    try:
        payload = json.dumps({
            "query": mutation,
            "variables": {"input": {"teamId": _TEAM_ID, "name": "cleanup", "color": "#A78BFA"}},
        }).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        return ((data.get("issueLabelCreate") or {}).get("issueLabel") or {}).get("id")
    except Exception as exc:
        log.warning("Cleanup label creation failed: %s", exc)
        return None


def _apply_label_to_issue(issue_id: str, label_id: str, api_key: str) -> bool:
    """Add a label to a Linear issue, preserving existing labels."""
    fetch_query = "query($id: String!) { issue(id: $id) { labels { nodes { id } } } }"
    try:
        payload = json.dumps({"query": fetch_query, "variables": {"id": issue_id}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        existing_ids = [
            n["id"] for n in
            (data.get("issue") or {}).get("labels", {}).get("nodes", [])
            if n.get("id")
        ]
    except Exception:
        existing_ids = []
    all_ids = list({*existing_ids, label_id})
    mutation = """
    mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) { success }
    }
    """
    try:
        payload = json.dumps({
            "query": mutation,
            "variables": {"id": issue_id, "input": {"labelIds": all_ids}},
        }).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        return bool((data.get("issueUpdate") or {}).get("success"))
    except Exception as exc:
        log.warning("Scout: label apply failed for issue %s: %s", issue_id, exc)
        return False


def _existing_scout_canonical(api_key: str) -> dict[str, dict[str, Any]] | None:
    """Fetch ALL [SCOUT] issues (open + terminal) and return {url: {id, identifier, state_type}}.

    Parses **URL:** from each issue description. Returns None on API failure so
    the caller can fail-closed (same pattern as _existing_scout_titles).
    """
    query = """
    query AllScoutIssues($projectId: ID!) {
        issues(
            filter: {
                project: { id: { eq: $projectId } },
                title: { startsWith: "[SCOUT]" }
            },
            first: 250
        ) { nodes { id identifier title description state { type } } }
    }
    """
    try:
        payload = json.dumps({"query": query, "variables": {"projectId": _PROJECT_ID}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read()).get("data", {})
        nodes = (data.get("issues") or {}).get("nodes", [])
        canonical: dict[str, dict[str, Any]] = {}
        for node in nodes:
            desc = node.get("description") or ""
            m = re.search(r"\*\*URL:\*\*\s*(\S+)", desc)
            if not m:
                continue
            url_key = m.group(1).strip().lower().rstrip(".")
            if url_key not in canonical:  # oldest/first = canonical keeper
                canonical[url_key] = {
                    "id": node["id"],
                    "identifier": node["identifier"],
                    "state_type": (node.get("state") or {}).get("type", ""),
                }
        log.info("Scout: canonical URL map: %d entries", len(canonical))
        return canonical
    except Exception as exc:
        log.warning("Scout: canonical URL fetch failed (%s) — failing closed", exc)
        return None


def _enrich_scout_issue(issue_id: str, finding: dict[str, Any], api_key: str) -> bool:
    """Add a re-detection comment to an existing SCOUT issue. Returns True on success."""
    source = finding.get("source", "").upper()
    dims = ", ".join(finding.get("matched_dims", [])) or "none"
    comment = (
        f"**Re-detected by scout** ({source})\n\n"
        f"**URL:** {finding.get('url', '')}\n"
        f"**Relevance:** {finding.get('relevance_score', 0)}/5  "
        f"**ZTE dimensions:** {dims}\n\n"
        f"_{finding.get('description', '')[:200]}_"
    )
    mutation = """
    mutation CommentCreate($input: CommentCreateInput!) {
        commentCreate(input: $input) { success }
    }
    """
    try:
        payload = json.dumps({
            "query": mutation,
            "variables": {"input": {"issueId": issue_id, "body": comment}},
        }).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        return bool((data.get("commentCreate") or {}).get("success"))
    except Exception as exc:
        log.warning("Scout: comment failed for issue %s: %s", issue_id, exc)
        return False


def _write_to_research_inbox(finding: dict[str, Any]) -> None:
    """Append a below-threshold finding to .harness/scout-research-inbox.jsonl."""
    try:
        _HARNESS.mkdir(parents=True, exist_ok=True)
        entry = {
            "source": finding.get("source", ""),
            "title": finding.get("title", ""),
            "url": finding.get("url", ""),
            "description": finding.get("description", "")[:300],
            "relevance_score": finding.get("relevance_score", 0),
            "matched_dims": finding.get("matched_dims", []),
        }
        with open(_RESEARCH_INBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log.warning("Scout: research inbox write failed: %s", exc)


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_scout_cycle(dry_run: bool = False) -> dict[str, Any]:
    """
    Run one full scout cycle. Returns:
      {"findings": N, "issues_created": [...], "sources": {"github": N, "arxiv": N, "hackernews": N}}
    Completes even if all sources fail.
    """
    log.info("Scout cycle starting (dry_run=%s)", dry_run)

    github_findings = fetch_github_findings()
    arxiv_findings = fetch_arxiv_findings()
    hn_findings = fetch_hn_findings()

    all_findings = github_findings + arxiv_findings + hn_findings
    sources_counts = {
        "github": len(github_findings),
        "arxiv": len(arxiv_findings),
        "hackernews": len(hn_findings),
    }
    log.info("Scout: total raw findings = %d", len(all_findings))

    seen = _load_seen()
    new_findings: list[dict[str, Any]] = []
    for finding in all_findings:
        item_id = _hash_id(finding["url"], finding["title"])
        if not _is_new(item_id, seen):
            continue
        score, matched_dims = _score_finding(finding["title"], finding["description"])
        finding["relevance_score"] = score
        finding["matched_dims"] = matched_dims
        finding["_id"] = item_id
        new_findings.append(finding)

    log.info("Scout: %d new (unseen) findings after dedup", len(new_findings))

    new_findings.sort(key=lambda f: f["relevance_score"], reverse=True)
    qualified = [f for f in new_findings if f["relevance_score"] >= _RELEVANCE_THRESHOLD]
    below_threshold = [f for f in new_findings if f["relevance_score"] < _RELEVANCE_THRESHOLD]
    # RA-6756: only file qualified findings to Linear; route the rest to research inbox
    top5 = qualified[:5]
    for low_f in below_threshold[:10]:
        _write_to_research_inbox(low_f)
    if below_threshold:
        log.info("Scout: %d below-threshold findings routed to research inbox", len(below_threshold))

    api_key = os.environ.get("LINEAR_API_KEY", "")
    label_id: str | None = None
    cleanup_label_id: str | None = None
    existing_titles: set[str] | None = set()
    canonical_by_url: dict[str, dict[str, Any]] | None = {}
    if api_key and not dry_run:
        label_id = _get_or_create_scout_label(api_key)
        cleanup_label_id = _get_or_create_cleanup_label(api_key)
        existing_titles = _existing_scout_titles(api_key)
        canonical_by_url = _existing_scout_canonical(api_key)
        if existing_titles is None:
            log.warning("Scout: Linear dedup unavailable — skipping issue "
                        "creation this cycle (fail-closed)")
        else:
            log.info("Scout: %d open [SCOUT] tickets already in Linear", len(existing_titles))

    issues_created: list[str] = []
    skipped_existing = 0
    for finding in top5:
        if existing_titles is None:
            break  # dedup source unavailable — never file blind (dupe storm guard)
        source = finding["source"].upper()
        candidate_title = f"[SCOUT] {source}: {finding['title'][:80]}".strip().lower()
        url_key = finding.get("url", "").strip().lower()

        # RA-6756: URL-based dedup takes priority — catches renamed/similar titles
        url_match = (canonical_by_url or {}).get(url_key) if url_key else None
        if url_match:
            state = url_match.get("state_type", "")
            if state in ("completed", "cancelled"):
                log.info(
                    "Scout: skip resolved %s for URL: %s",
                    url_match["identifier"], url_key[:60],
                )
                skipped_existing += 1
                continue
            # Open canonical → enrich with comment + cleanup label
            _enrich_scout_issue(url_match["id"], finding, api_key)
            if cleanup_label_id:
                _apply_label_to_issue(url_match["id"], cleanup_label_id, api_key)
            log.info("Scout: enriched %s for URL: %s", url_match["identifier"], url_key[:60])
            skipped_existing += 1
            continue

        # Title-based dedup (fail-closed guard from 2026-06 dupe storm fix)
        if candidate_title in existing_titles:
            log.info("Scout: skipping duplicate of open Linear ticket — %s", finding["title"][:60])
            skipped_existing += 1
            continue

        if dry_run:
            log.info("[DRY RUN] Would create issue for %s: %s", finding["source"], finding["title"][:60])
            issues_created.append(f"[DRY RUN] {finding['source']}: {finding['title'][:60]}")
        else:
            if not api_key:
                log.warning("LINEAR_API_KEY not set — skipping issue creation")
                break
            identifier = _create_linear_issue(finding, label_id, api_key)
            if identifier:
                issues_created.append(identifier)
                existing_titles.add(candidate_title)

    # Update seen list only for all new findings processed this cycle (not just top5)
    for finding in new_findings:
        seen = _add_seen(finding["_id"], seen)
    try:
        _save_seen(seen)
    except Exception as exc:
        log.warning("Scout: failed to save seen cache: %s", exc)

    result = {
        "findings": len(new_findings),
        "issues_created": issues_created,
        "skipped_existing": skipped_existing,
        "sources": sources_counts,
    }
    log.info("Scout cycle complete: %s", result)
    return result
