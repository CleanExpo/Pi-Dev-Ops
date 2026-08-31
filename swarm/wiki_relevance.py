"""swarm/wiki_relevance.py — requirement-aware target selection for wiki ingestion.

`_identify_targets` used to live in `wiki_ingest.py` and chose its ≤5 target pages
from `index.md` alone. That means it knew what the wiki ALREADY CONTAINS and
nothing about what the projects NEED, which makes "is this source relevant?"
unanswerable: every source looks equally on-topic to a chooser with no statement
of intent to compare against.

`project_requirements` (shipped in #697) is that statement. This module is the
consumer it was missing — until now `active_requirements()` had exactly one
caller, the endpoint that read it straight back out, so the registry influenced
no ingestion decision at all.

Moved here rather than extended in place because `swarm/wiki_ingest.py` sits at
exactly its 431-line baseline entry and the size gate fails a baselined file that
grows. Extracting is the documented fix, and it ratchets the baseline down.

TWO THINGS THIS MODULE IS NOT:

  * It is not a security control. Relevance decides ROUTING — ingest now, or park
    for a human. The finding is attacker-controlled and could try to inflate its
    own score; that buys it nothing, because `ingest_guard.screen()` still
    validates every target before a single write. A finding that talks its score
    DOWN merely quarantines itself, which is harmless.
  * It is not a filter that can fail closed. Every ambiguity resolves toward
    INGESTING: an empty registry skips the gate, an unparseable score counts as
    maximally relevant. A relevance signal that silently swallowed good sources
    would be far worse than one that occasionally lets a marginal one through,
    and the caller cannot tell a real "not relevant" from a broken scorer.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Optional

from . import ingest_guard

log = logging.getLogger("swarm.wiki_relevance")

# Scored 0–10 by the same LLM call that picks the targets. Folded into that
# prompt rather than issued separately: it already carries the finding and the
# index, so a second call would double cost and latency for one integer.
RELEVANCE_MAX = 10

# Deliberately permissive. This gate exists to catch the clearly-off-topic, not
# to curate — a threshold high enough to be opinionated would quietly reshape
# the wiki according to whatever the requirements happened to say that week.
DEFAULT_RELEVANCE_THRESHOLD = 3

# config/harness/projects.json `id`, never a repo: `id` is unique across all 12
# entries and `repo` is not — CleanExpo/Pi-Dev-Ops deliberately carries both
# `pi-dev-ops` and `margot`, so a repo-keyed lookup silently picks one.
DEFAULT_PROJECT_KEY = "pi-dev-ops"

_PROJECT_FM = re.compile(r'^project:\s*"?([A-Za-z0-9][A-Za-z0-9._-]*)"?\s*$', re.MULTILINE)


def relevance_threshold() -> int:
    """Read per call so it can be tuned without a redeploy."""
    try:
        return int(os.environ.get("WIKI_RELEVANCE_THRESHOLD", DEFAULT_RELEVANCE_THRESHOLD))
    except ValueError:
        log.warning("WIKI_RELEVANCE_THRESHOLD is not an integer — using the default")
        return DEFAULT_RELEVANCE_THRESHOLD


def split_frontmatter(raw: str) -> tuple[str, Optional[str]]:
    """(body, frontmatter) — the YAML block stripped off a source file.

    Lives here beside `project_key_for()`, which is its only reason to exist: the
    frontmatter has to be captured BEFORE it is cut off the text, or the project
    key is read from a string that no longer contains it.
    """
    if not raw.startswith("---"):
        return raw, None
    end = raw.find("\n---", 3)
    if end == -1:
        return raw, None
    return raw[end + 4:].lstrip(), raw[3:end]


def project_key_for(frontmatter: Optional[str]) -> str:
    """Which project's requirements this source is scored against.

    A source file may name one in its frontmatter (`project: margot`); otherwise
    `WIKI_PROJECT_KEY`, otherwise the default. The override exists because this
    repo carries two Linear projects, so an env-only answer would score every
    margot clip against pi-dev-ops requirements.
    """
    if frontmatter:
        m = _PROJECT_FM.search(frontmatter)
        if m:
            return m.group(1)
    return os.environ.get("WIKI_PROJECT_KEY", "").strip() or DEFAULT_PROJECT_KEY


def fetch_requirements(project_key: str) -> list[dict[str, Any]]:
    """What this project needs, or `[]` if that cannot be answered.

    `[]` on ANY failure, including an unimportable `app` package: the registry is
    optional context for target selection, and `below_threshold()` treats an
    empty list as "no basis to judge" and skips the gate. So a Supabase outage
    degrades ingestion to exactly its pre-#697 behaviour rather than stopping it.

    Imported lazily because `swarm/` is importable on machines that do not run
    the FastAPI app, and an import-time dependency would take the whole wiki
    pipeline down with it.
    """
    try:
        from app.server import wiki_source_store  # noqa: PLC0415

        return wiki_source_store.active_requirements(project_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_relevance: requirements unavailable (%s) — gate off", exc)
        return []


def _requirements_block(requirements: list[dict[str, Any]]) -> str:
    """Render requirements for the prompt.

    NOT fenced, deliberately. `fence_source()` marks text as untrusted DATA that
    must never be followed; these rows arrived through an authenticated route and
    are ours. Fencing them would tell the model to disregard the very thing it is
    being asked to judge against, and would blunt the signal that makes fencing
    meaningful for the finding — which stays fenced exactly as before.
    """
    lines = []
    for r in requirements:
        title = str(r.get("title") or "").strip()
        if not title:
            continue
        detail = str(r.get("detail") or "").strip()
        kw = r.get("keywords") or []
        parts = [f"- {title}"]
        if detail:
            parts.append(f"  {detail}")
        if isinstance(kw, list) and kw:
            parts.append(f"  keywords: {', '.join(str(k) for k in kw[:12])}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


def _build_prompt(finding: str, index: str, requirements: list[dict[str, Any]]) -> str:
    """The targeting prompt, with a relevance ask only when there is a basis for one."""
    block = _requirements_block(requirements)
    relevance_ask = ""
    relevance_field = ""
    if block:
        relevance_ask = (
            "\n\nThe project currently needs the following. Judge how much the "
            "finding helps with any of it:\n" + block
        )
        relevance_field = (
            ', "relevance": <integer 0-10, how much the finding serves the needs above; '
            "10 = directly addresses one, 0 = entirely unrelated>"
        )
    return (
        "You are updating a personal knowledge wiki. Given the finding below "
        "and the wiki index, identify which pages to update."
        f"{relevance_ask}\n\n"
        f"Wiki index:\n{ingest_guard.fence_source(index, label='wiki index')}\n\n"
        f"{ingest_guard.fence_source(finding, label='finding')}\n\n"
        "Reply with JSON only (no markdown fences):\n"
        '{"update": ["filename.md", ...], '
        '"create": {"slug": "new-page-slug", "description": "one-line", "section": "## Section"} | null'
        f"{relevance_field}}}\n"
        "Rules: update ≤5 files. create is null if no new page is needed. "
        "Only name files that actually appear in the index. "
        "NEVER include index.md or log.md — those are managed by the system."
    )


def _parse(raw: str) -> dict[str, Any]:
    """The original tolerant JSON parse, unchanged in behaviour."""
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {"update": [], "create": None}


def identify_targets(
    finding: str,
    index: str,
    requirements: list[dict[str, Any]],
    call_llm: Callable[[str], str],
) -> dict[str, Any]:
    """Which pages to update, and how relevant the finding is.

    `call_llm` is injected rather than imported so this module does not import
    back into `wiki_ingest` (which imports it), and so tests exercise the real
    prompt-building and parsing without a network.
    """
    result = _parse(call_llm(_build_prompt(finding, index, requirements)))
    result["relevance"] = _coerce_relevance(result.get("relevance"))
    return result


def _coerce_relevance(value: Any) -> int:
    """A 0–10 score. Anything unreadable counts as MAXIMALLY relevant.

    Fail-open on purpose: a missing or malformed score means the scorer did not
    answer, not that the source is off-topic. Defaulting low would let one bad
    LLM response quarantine a legitimate document, and the difference is
    invisible to whoever reviews the quarantine folder later.
    """
    try:
        return max(0, min(int(value), RELEVANCE_MAX))
    except (TypeError, ValueError):
        return RELEVANCE_MAX


def below_threshold(targets: dict[str, Any], requirements: list[dict[str, Any]]) -> bool:
    """True only when there IS a basis to judge and the finding fell short.

    `requirements` being empty is the state of every deployment that has not
    filled the registry in, and it is also what `active_requirements()` returns
    when Supabase is unreachable. Both must skip the gate entirely — otherwise
    the first deploy quarantines every document against an empty requirement set,
    and a database outage silently stops the whole ingest pipeline.
    """
    if not requirements:
        return False
    return _coerce_relevance(targets.get("relevance")) < relevance_threshold()


__all__ = [
    "fetch_requirements", "split_frontmatter",
    "identify_targets", "below_threshold", "project_key_for", "relevance_threshold",
    "RELEVANCE_MAX", "DEFAULT_RELEVANCE_THRESHOLD", "DEFAULT_PROJECT_KEY",
]
