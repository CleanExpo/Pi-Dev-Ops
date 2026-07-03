"""
open_skill_pr.py — PR-opening step for skill self-improvement (RA-continuous-moa §6.5)

Pi-Dev-Ops-scoped reimplementation of the pr-creator pattern (branch -> commit
-> push -> gh pr create), targeting Pi-Dev-Ops's own base branch (main) and
title/label convention, rather than RestoreAssist's pr-creator subagent (which
is hardcoded to base=sandbox and RA-XXX Linear refs and has no target-repo
parameter — see Task 5 note in the plan).

Never merges. Only opens a PR on a new feature branch, per design §6's hard
constraint: never edits a SKILL.md directly on disk outside a PR branch, and
never self-merges.

dry_run support: open_pr() accepts dry_run=True to exercise the full
branch/commit/PR-title/label-building logic WITHOUT ever invoking git/gh —
tests (and any caller that wants a preview) use this so no real branch,
commit, push, or PR is ever created as a side effect of running this module.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_REPO = "CleanExpo/Pi-Dev-Ops"
_LABEL = "skill-self-update"
_LABEL_DESCRIPTION = "Auto-drafted SKILL.md fix from a recurring skill-process lesson"
_LABEL_COLOR = "5319e7"
_BASE_BRANCH = "main"
_MAX_TITLE_LEN = 100


def _first_lesson_summary(lessons: list[dict]) -> str:
    if not lessons:
        return "skill process update"
    text = lessons[0].get("lesson", "skill process update").strip()
    return text


def pr_title(skill_name: str, lessons: list[dict]) -> str:
    summary = _first_lesson_summary(lessons)
    prefix = f"skill-learn({skill_name}): "
    available = _MAX_TITLE_LEN - len(prefix)
    if len(summary) > available:
        summary = summary[: available - 1].rstrip() + "…"
    return prefix + summary


def branch_name(skill_name: str) -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"skill-self-update/{skill_name}-{date_str}"


def pr_body(skill_name: str, lessons: list[dict]) -> str:
    lines = [
        f"## Auto-drafted skill-process fix for `{skill_name}`",
        "",
        "This PR was opened automatically by the skill self-improvement loop "
        "(`scripts/skill_self_update.py`) after recurring lessons flagged this "
        "skill's own process/instructions as a source of confusion.",
        "",
        "### Triggering lesson(s)",
        "",
    ]
    for entry in lessons:
        severity = entry.get("severity", "info")
        source = entry.get("source", "unknown")
        ts = entry.get("ts", "unknown")
        lines.append(f"- [{severity}, from `{source}`, {ts}] {entry.get('lesson', '')}")
    lines += [
        "",
        "### Review required",
        "",
        "This diff is auto-generated and passed the mechanical subset of "
        "`skill-authoring-standard`'s review checklist (line count, banned "
        "frontmatter fields, single-file scope). It has NOT been checked for "
        "duplication, leading-word steering, or sediment — a human reviewer "
        "must confirm those before merging. Never self-merges.",
    ]
    return "\n".join(lines)


def ensure_label_exists(repo: str = _REPO, dry_run: bool = False) -> None:
    if dry_run:
        return
    result = subprocess.run(
        ["gh", "label", "list", "--repo", repo],
        capture_output=True, text=True, check=False,
    )
    existing = {line.split("\t")[0] for line in result.stdout.splitlines() if line.strip()}
    if _LABEL in existing:
        return
    subprocess.run(
        [
            "gh", "label", "create", _LABEL,
            "--repo", repo,
            "--description", _LABEL_DESCRIPTION,
            "--color", _LABEL_COLOR,
        ],
        capture_output=True, text=True, check=False,
    )


def open_pr(
    skill_name: str,
    diff_text: str,
    lessons: list[dict],
    repo_path: Path = _ROOT,
    dry_run: bool = False,
) -> str:
    """Create branch, apply diff, commit, push, open PR. Returns the PR URL.
    Raises RuntimeError on any git/gh failure (caller decides how to log it).

    When dry_run=True, no git/gh commands are executed — the branch name,
    title, and body are computed and returned as a descriptive string so
    callers (and tests) can exercise the full decision logic without any
    real side effects.
    """
    branch = branch_name(skill_name)
    title = pr_title(skill_name, lessons)
    body = pr_body(skill_name, lessons)

    if dry_run:
        ensure_label_exists(dry_run=True)
        return f"DRY_RUN: would open PR '{title}' on branch '{branch}' with label '{_LABEL}'"

    ensure_label_exists()

    skill_md_relpath = f"skills/{skill_name}/SKILL.md"

    subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "pull", "--ff-only"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo_path, check=True, capture_output=True)

    apply_result = subprocess.run(
        ["git", "apply", "-"], cwd=repo_path, input=diff_text, text=True, capture_output=True,
    )
    if apply_result.returncode != 0:
        raise RuntimeError(f"git apply failed for {skill_name}: {apply_result.stderr}")

    subprocess.run(["git", "add", skill_md_relpath], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"skill-learn({skill_name}): auto-drafted process fix"],
        cwd=repo_path, check=True, capture_output=True,
    )
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=repo_path, check=True, capture_output=True)

    pr_result = subprocess.run(
        [
            "gh", "pr", "create",
            "--repo", _REPO,
            "--base", _BASE_BRANCH,
            "--head", branch,
            "--title", title,
            "--body", body,
            "--label", _LABEL,
        ],
        cwd=repo_path, check=True, capture_output=True, text=True,
    )
    return pr_result.stdout.strip()
