"""STORM evidence adapter — perspectives + repo/LLM evidence rows for judge."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from .llm import complete, parse_json_object
from .prebuild_judge import EvidenceRow

log = logging.getLogger("pi-ceo.spec_pipeline.storm_evidence")

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_PERSPECTIVES = (
    ("architect", "What existing code and patterns apply?"),
    ("security", "What auth, secrets, and boundary risks exist?"),
    ("skeptic", "What could fail or be over-scoped?"),
    ("operator", "What is the smallest reversible version?"),
)


def _repo_grep(keyword: str, limit: int = 8) -> list[str]:
    if not keyword or len(keyword) < 3:
        return []
    try:
        proc = subprocess.run(
            ["rg", "-l", "-i", keyword[:40], "app", "dashboard", "skills", "tests"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        return lines[:limit]
    except (subprocess.SubprocessError, OSError):
        return []


def _keywords_from_proposal(proposal: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", proposal.lower())
    stop = {"with", "that", "this", "from", "into", "when", "what", "will", "need", "build"}
    return [t for t in tokens if t not in stop][:12]


async def gather_evidence(proposal: str) -> list[EvidenceRow]:
    """Gather structured evidence rows (repo + LLM; no full STORM article)."""
    hits: list[dict[str, str]] = []
    for kw in _keywords_from_proposal(proposal):
        for path in _repo_grep(kw):
            hits.append({
                "claim": f"Repo mentions '{kw}' in {path}",
                "source_url": f"file://{REPO_ROOT / path}",
                "source_title": path,
                "perspective": "architect",
            })

    pers_lines = "\n".join(
        f"- {label}: {question}" for label, question in DEFAULT_PERSPECTIVES
    )
    prompt = (
        "Produce JSON only. Given a build proposal and repo file hits, "
        "return evidence rows for a judge table.\n\n"
        f"Proposal:\n{proposal}\n\n"
        f"Perspectives:\n{pers_lines}\n\n"
        f"Repo hits ({len(hits)}):\n"
        + "\n".join(f"- {h['claim']}" for h in hits[:30])
        + "\n\nSchema: "
        '{"rows":[{"claim":"","source_url":"","source_title":"","perspective":"","status":"SUPPORTED|PARTIAL|UNSUPPORTED|NOT CHECKED"}]}'
    )
    try:
        text, _ = await complete(prompt=prompt, role="storm_evidence", max_tokens=2000)
        data = parse_json_object(text)
        rows: list[EvidenceRow] = []
        for row in data.get("rows") or []:
            if not isinstance(row, dict):
                continue
            rows.append(EvidenceRow(
                claim=str(row.get("claim", "")),
                source_url=str(row.get("source_url", "")),
                source_title=str(row.get("source_title", "")),
                perspective=str(row.get("perspective", "")),
                status=str(row.get("status", "SUPPORTED")).upper(),
            ))
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("storm evidence LLM failed: %s", exc)

    # Deterministic fallback from grep hits
    return [
        EvidenceRow(
            claim=h["claim"],
            source_url=h["source_url"],
            source_title=h["source_title"],
            perspective=h["perspective"],
            status="SUPPORTED",
        )
        for h in hits[:20]
    ] or [
        EvidenceRow(
            claim="No repo evidence auto-located; manual verification required",
            status="NOT CHECKED",
            perspective="skeptic",
        )
    ]
