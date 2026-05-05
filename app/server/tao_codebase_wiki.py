"""app/server/tao_codebase_wiki.py — RA-1968: self-updating per-directory WIKI.md.

Port of `@0xkobold/pi-codebase-wiki`. Reads recent git history, groups commits
by top-level directory, and asks the SDK (sonnet, role=scribe) to refresh a
compact `<dir>/WIKI.md`. Wave 1 (epic RA-1965); sibling of RA-1966
(`kill_switch`), RA-1967 (`tao_context_vcc`), RA-1970 (tao-judge / tao-loop).

Public API: `update_wiki(repo_root, since_ref=None, max_cost_usd=0.02,
dry_run=False, directories=None) -> WikiUpdateResult`.

Cost-budget guard runs BEFORE any SDK call. Kill-switch is checked per
directory iteration. On hard-stop or budget overrun, returns a populated
`WikiUpdateResult` with `bypassed=True` and a reason code.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .kill_switch import KillSwitchAbort, LoopCounter

log = logging.getLogger("pi-ceo.tao_codebase_wiki")

# Pricing per https://docs.anthropic.com/en/docs/about-claude/models — sonnet
# 4.6 = $3/M input + $15/M output.
_SONNET_INPUT: float = 3.0 / 1_000_000
_SONNET_OUTPUT: float = 15.0 / 1_000_000
_DEFAULT_COMPLETION_TOKENS: int = 1500
_BYTES_PER_TOKEN: int = 4

_LAST_UPDATE_RE = re.compile(
    r"_Last updated: (?P<ts>\S+) \(commits (?P<old>[0-9a-f]+)\.\.(?P<new>[0-9a-f]+)\)_"
)
_DEFAULT_FALLBACK_DEPTH: int = 50


@dataclass
class WikiUpdateResult:
    directories_updated: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    commits_summarized: int = 0
    cost_usd_estimate: float = 0.0
    bypassed: bool = False
    bypass_reason: str | None = None


@dataclass
class _Commit:
    sha: str
    subject: str
    files: list[str]


def _git(repo_root: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_root, *args], check=True, capture_output=True, text=True
    )
    return proc.stdout


def _find_last_recorded_sha(wiki_path: Path) -> str | None:
    if not wiki_path.is_file():
        return None
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        m = _LAST_UPDATE_RE.search(line)
        if m:
            return m.group("new")
    return None


def _resolve_since_ref(repo_root: str, explicit: str | None) -> str:
    """Pick commit range start. Explicit > recorded > HEAD~N fallback."""
    if explicit:
        return explicit
    root_sha = _find_last_recorded_sha(Path(repo_root) / "WIKI.md")
    if root_sha:
        return root_sha
    try:
        count = int(_git(repo_root, "rev-list", "--count", "HEAD").strip() or "0")
    except (subprocess.CalledProcessError, ValueError):
        count = 0
    depth = min(_DEFAULT_FALLBACK_DEPTH, max(count - 1, 0))
    return f"HEAD~{depth}" if depth > 0 else ""


def _collect_commits(repo_root: str, since_ref: str) -> list[_Commit]:
    rev_range = f"{since_ref}..HEAD" if since_ref else "HEAD"
    try:
        out = _git(
            repo_root, "log", rev_range, "--pretty=format:%H|%s", "--name-only"
        )
    except subprocess.CalledProcessError as exc:
        log.warning("git log failed for range=%r: %s", rev_range, exc)
        return []
    commits: list[_Commit] = []
    for block in [b for b in out.split("\n\n") if b.strip()]:
        lines = block.splitlines()
        parts = lines[0].split("|", 1)
        if len(parts) != 2:
            continue
        files = [ln.strip() for ln in lines[1:] if ln.strip()]
        commits.append(_Commit(sha=parts[0], subject=parts[1], files=files))
    return commits


def _group_by_top_dir(commits: list[_Commit]) -> dict[str, list[_Commit]]:
    grouped: dict[str, list[_Commit]] = {}
    for c in commits:
        seen: set[str] = set()
        for f in c.files:
            if f.endswith("WIKI.md"):
                continue
            top = f.split("/", 1)[0]
            if top in seen:
                continue
            seen.add(top)
            grouped.setdefault(top, []).append(c)
    return grouped


def _read_short_context(repo_root: str, top_dir: str) -> str:
    base = Path(repo_root) / top_dir
    parts: list[str] = []
    for name in ("SKILL.md", "README.md", "WIKI.md"):
        p = base / name
        if p.is_file():
            try:
                head = "\n".join(p.read_text(encoding="utf-8").splitlines()[:30])
                parts.append(f"# {name}\n{head}")
            except OSError:
                continue
    return "\n\n".join(parts)[:1500]


def _build_prompt(top_dir: str, commits: list[_Commit], context: str) -> str:
    bullets = []
    for c in commits[:20]:
        files_brief = ", ".join(c.files[:5])
        if len(c.files) > 5:
            files_brief += f", +{len(c.files) - 5} more"
        bullets.append(f"- {c.sha[:7]} — {c.subject} (files: {files_brief})")
    return (
        f"You are updating the WIKI.md for the `{top_dir}/` directory of a "
        "Python/TypeScript codebase.\n\n"
        "Output ONLY the body of these sections (no preamble):\n"
        "## Architecture (current)\n"
        "<one short paragraph synthesising what this directory does>\n\n"
        "## Files of interest\n"
        "<bullet list, 4-8 entries, each `- path — one-line purpose`>\n\n"
        f"Existing context:\n{context or '(none)'}\n\n"
        f"Recent commits affecting `{top_dir}/`:\n" + "\n".join(bullets) + "\n"
    )


def _estimate_cost_usd(prompt: str) -> float:
    """Rough $$$ estimate for a single sonnet 4.6 call."""
    prompt_tokens = max(1, len(prompt.encode("utf-8")) // _BYTES_PER_TOKEN)
    return prompt_tokens * _SONNET_INPUT + _DEFAULT_COMPLETION_TOKENS * _SONNET_OUTPUT


def _format_recent_changes(commits: list[_Commit]) -> str:
    return "\n".join(f"- {c.sha[:7]} — {c.subject}" for c in commits[:8])


def _render_wiki(top_dir: str, old_sha: str, new_sha: str, commits: list[_Commit], body: str, timestamp_iso: str) -> str:
    return (
        f"# {top_dir} — Wiki\n\n"
        f"_Last updated: {timestamp_iso} (commits {old_sha}..{new_sha})_\n\n"
        f"## Recent changes\n{_format_recent_changes(commits)}\n\n"
        f"{body.strip()}\n"
    )


def _run_scribe_sync(prompt: str) -> str:
    """Invoke the SDK runner. Returns text body or "" on failure."""
    try:
        from .session_sdk import _run_claude_via_sdk  # noqa: PLC0415
        from . import config  # noqa: PLC0415
    except ImportError as exc:
        log.warning("scribe SDK import failed: %s", exc)
        return ""
    model_id = config.MODEL_SHORT_TO_ID.get("sonnet", "sonnet")
    try:
        rc, text, _ = asyncio.run(
            _run_claude_via_sdk(
                prompt=prompt,
                model=model_id,
                workspace=os.getcwd(),
                timeout=120,
                phase="scribe.wiki",
                thinking="disabled",
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("scribe SDK call failed: %s", exc)
        return ""
    return text if rc == 0 and text else ""


def _stub_body(top_dir: str, commits: list[_Commit]) -> str:
    """SDK-unavailable fallback. Keeps the WIKI.md format stable."""
    files: list[str] = []
    for c in commits:
        for f in c.files:
            if f.startswith(f"{top_dir}/") and f not in files:
                files.append(f)
    bullets = "\n".join(f"- {f} — touched in recent commits" for f in files[:6]) or "- (no files listed)"
    return (
        "## Architecture (current)\n"
        f"Auto-stub: `{top_dir}/` had {len(commits)} recent commits. "
        "SDK unavailable for synthesis.\n\n"
        "## Files of interest\n"
        f"{bullets}"
    )


def _resolve_head_short(repo: str) -> str:
    try:
        return _git(repo, "rev-parse", "HEAD").strip()[:7]
    except subprocess.CalledProcessError:
        return "HEAD"


def update_wiki(repo_root: str, since_ref: str | None = None, max_cost_usd: float = 0.02, dry_run: bool = False, directories: list[str] | None = None) -> WikiUpdateResult:
    """Refresh per-directory `WIKI.md` files based on recent git history."""
    result = WikiUpdateResult()
    repo = str(Path(repo_root).resolve())
    since = _resolve_since_ref(repo, since_ref)
    commits = _collect_commits(repo, since)
    if not commits:
        return result
    grouped = _group_by_top_dir(commits)
    if directories:
        wanted = set(directories)
        grouped = {k: v for k, v in grouped.items() if k in wanted}
    if not grouped:
        return result

    head_sha = _resolve_head_short(repo)
    old_sha = since[:7] if since and not since.startswith("HEAD~") else "init"
    counter = LoopCounter()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_commits = {c.sha for c in commits}

    for top_dir, dir_commits in sorted(grouped.items()):
        try:
            counter.tick(cost_delta_usd=0.0)
        except KillSwitchAbort as abort:
            result.bypassed = True
            result.bypass_reason = f"kill_switch:{abort.reason}"
            return result
        context = _read_short_context(repo, top_dir)
        prompt = _build_prompt(top_dir, dir_commits, context)
        cost_estimate = _estimate_cost_usd(prompt)
        if cost_estimate > max_cost_usd:
            result.bypassed = True
            result.bypass_reason = "cost_budget_exceeded"
            return result
        result.cost_usd_estimate += cost_estimate
        if dry_run:
            result.directories_updated.append(top_dir)
            continue
        body = _run_scribe_sync(prompt) or _stub_body(top_dir, dir_commits)
        rendered = _render_wiki(top_dir, old_sha, head_sha, dir_commits, body, timestamp)
        wiki_path = Path(repo) / top_dir / "WIKI.md"
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text(rendered, encoding="utf-8")
        result.directories_updated.append(top_dir)
        result.files_written.append(str(wiki_path.relative_to(repo)))

    result.commits_summarized = len(total_commits)
    return result


__all__ = ["WikiUpdateResult", "update_wiki"]
