"""
skill_self_update.py — End-to-end orchestrator for skill self-improvement
(RA-continuous-moa §6, composes Tasks 2-5)

Chains: scan_skill_lessons.find_flagged_skills -> draft_skill_diff.build_dispatch_prompt
-> [caller-supplied LLM dispatch] -> review_skill_diff.review_diff -> open_skill_pr.open_pr

This module cannot call the Agent tool itself (that tool only exists inside a
live Claude Code session). The session that runs a self-improvement cycle
imports run_cycle() and passes its own Agent-tool-backed dispatch function as
`dispatch_fn`. No standing cron calls this directly — per design §2/§3, this
loop is invoked only from within a session, same as the rest of the continuous
MOA loop it composes with.

dry_run: run_cycle(..., dry_run=True) runs the full scan -> draft -> review
chain and, for any diff that passes review, calls open_pr(..., dry_run=True)
instead of actually creating a branch/commit/PR — so a full cycle can be
exercised end-to-end (including what WOULD be opened) with zero real git/gh
side effects. This is also exactly how the test suite exercises run_cycle():
tests monkeypatch open_pr directly, so dry_run is an additional safety layer
for any non-test caller that wants a preview.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from scripts.draft_skill_diff import build_dispatch_prompt, write_draft  # noqa: E402
from scripts.open_skill_pr import open_pr  # noqa: E402
from scripts.review_skill_diff import review_diff  # noqa: E402
from scripts.scan_skill_lessons import find_flagged_skills, group_by_skill, load_skill_lessons  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pi-ceo.skill-self-update")

_HARNESS = _ROOT / ".harness"
_DEFAULT_LESSONS_PATH = _HARNESS / "lessons.jsonl"


def _skill_md_path(skill_name: str) -> Path:
    return _ROOT / "skills" / skill_name / "SKILL.md"


def run_cycle(
    lessons_path: Path,
    dispatch_fn: Callable[[str], str],
    min_count: int = 3,
    window_days: int = 30,
    dry_run: bool = False,
) -> list[dict]:
    lessons = load_skill_lessons(lessons_path)
    groups = group_by_skill(lessons)
    flagged = find_flagged_skills(groups, min_count=min_count, window_days=window_days)

    results: list[dict] = []

    for skill_name, entries in flagged.items():
        skill_md_path = _skill_md_path(skill_name)
        if not skill_md_path.exists():
            log.warning("Flagged skill %s has no SKILL.md at %s — skipping", skill_name, skill_md_path)
            results.append({
                "skill": skill_name,
                "outcome": "rejected",
                "detail": f"SKILL.md not found at {skill_md_path}",
            })
            continue

        prompt = build_dispatch_prompt(skill_name, skill_md_path, entries)
        diff_text = dispatch_fn(prompt)

        if diff_text.strip() == "NO_CHANGE_JUSTIFIED":
            log.info("Skill %s: drafting agent found no change justified", skill_name)
            results.append({
                "skill": skill_name,
                "outcome": "no_change_justified",
                "detail": "Drafting agent determined lessons did not justify a change.",
            })
            continue

        write_draft(skill_name, diff_text)

        review_result = review_diff(diff_text, skill_md_path)
        if not review_result.passed:
            log.info("Skill %s: diff rejected — %s", skill_name, "; ".join(review_result.failures))
            results.append({
                "skill": skill_name,
                "outcome": "rejected",
                "detail": "; ".join(review_result.failures),
            })
            continue

        if dry_run:
            pr_url = open_pr(skill_name, diff_text, entries, dry_run=True)
        else:
            pr_url = open_pr(skill_name, diff_text, entries)
        log.info("Skill %s: PR opened — %s", skill_name, pr_url)
        results.append({
            "skill": skill_name,
            "outcome": "pr_opened",
            "detail": pr_url,
        })

    return results


if __name__ == "__main__":
    log.error(
        "skill_self_update.py has no standalone entry point — it must be invoked "
        "from a live Claude Code session that supplies an Agent-tool-backed "
        "dispatch_fn. Import run_cycle() instead of running this script directly."
    )
    sys.exit(1)
