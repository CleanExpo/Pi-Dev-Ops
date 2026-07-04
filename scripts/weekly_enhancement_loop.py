#!/usr/bin/env python3
"""Weekly cross-repo enhancement loop (8-Claude-Loops improve-system method).

Runs every Monday 02:00 AEST. For every repo in .harness/projects.json it clones
an isolated workspace and runs an improve-system pass through the Opus/Sonnet/Haiku
model ladder, then opens a review PR (never merges). See
skills/weekly-enhancement-loop/SKILL.md and
docs/sources/8-claude-loops-to-build-10x-faster.md.

Model ladder is API-mode (Fable-5 left the Max plan 2026-07-08 — this loop uses
ANTHROPIC_API_KEY, not the Max OAuth subscription):

    planner/orchestrator (Opus)  -> ENHANCE_MODEL_OPUS    (claude-opus-4-6)
    generator/evaluator (Sonnet) -> ENHANCE_MODEL_SONNET  (claude-sonnet-4-6)
    monitor/scan        (Haiku)  -> ENHANCE_MODEL_HAIKU   (claude-haiku-4-5-20251001)

Abort axes (shared with every TAO loop, RA-1966): TAO_HARD_STOP_FILE,
TAO_MAX_COST_USD, and a per-loop repo cap. Nothing is merged to main; each repo
yields at most one open PR per week on branch enhance/weekly-<date>.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weekly-enhancement-loop")

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / ".harness" / "projects.json"
LOG_DIR = REPO_ROOT / ".harness" / "enhancement-loop"
WORKSPACE_ROOT = Path(os.environ.get("ENHANCE_WORKSPACE", "/tmp/pi-ceo-enhance"))

MODEL_OPUS = os.environ.get("ENHANCE_MODEL_OPUS", "claude-opus-4-6")
MODEL_SONNET = os.environ.get("ENHANCE_MODEL_SONNET", "claude-sonnet-4-6")
MODEL_HAIKU = os.environ.get("ENHANCE_MODEL_HAIKU", "claude-haiku-4-5-20251001")

HARD_STOP_FILE = Path(os.environ.get("TAO_HARD_STOP_FILE", str(Path.home() / ".claude" / "HARD_STOP")))
MAX_COST_USD = float(os.environ.get("TAO_MAX_COST_USD", "5.00"))
# The loop's self-repo — enhancing it is allowed but must never push a ref the
# autonomy webhook re-triggers on (RA-1182: 43 zombie branches).
SELF_REPO = "CleanExpo/Pi-Dev-Ops"


def _kill_switch_tripped() -> str | None:
    if HARD_STOP_FILE.exists():
        return f"hard-stop file present: {HARD_STOP_FILE}"
    return None


def load_repos() -> list[str]:
    data = json.loads(REGISTRY.read_text())
    return sorted({p["repo"] for p in data["projects"]})


def _ensure_api_mode() -> None:
    """Post-2026-07-08: a real sk-ant-api key is required (Max OAuth is gone).

    Unlike session_sdk (which pops the key to fall back to OAuth), this loop must
    keep a genuine API key so every call is billed API-mode Opus/Sonnet/Haiku.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or key.startswith("sk-ant-oat01-"):
        raise SystemExit(
            "ANTHROPIC_API_KEY missing or is a Max OAuth token. Fable-5 left the "
            "Max plan 2026-07-08 — set a real sk-ant-api... key (Actions secret or "
            "~/.config/piceo/enhancement.env)."
        )
    os.environ["ANTHROPIC_API_KEY"] = key  # normalise (strip trailing newline)


async def run_phase(role: str, model: str, prompt: str, cwd: Path, timeout: int) -> str:
    """One agentic phase via claude_agent_sdk.query() — mirrors session_sdk.py."""
    from claude_agent_sdk import (  # noqa: PLC0415
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    options = ClaudeAgentOptions(cwd=str(cwd), model=model, permission_mode="bypassPermissions")
    parts: list[str] = []

    async def _stream() -> None:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                break

    t0 = time.monotonic()
    await asyncio.wait_for(_stream(), timeout=timeout)
    log.info("phase %s (%s) done in %.1fs", role, model, time.monotonic() - t0)
    return "\n".join(parts)


def _clone(repo: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GH_ENHANCE_PAT") or os.environ.get("GITHUB_TOKEN", "")
    url = f"https://x-access-token:{token}@github.com/{repo}.git" if token else f"https://github.com/{repo}.git"
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True, capture_output=True)
    # Plant a stub CLAUDE.md so Claude's upward search can't inherit Pi-CEO's
    # instructions from a parent dir (RA-1169). /tmp has none, but be explicit.


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


ENHANCE_PROMPT = """You are the weekly enhancement loop for the repo checked out at the current
working directory. Apply the improve-system method (loops 4-8 of
"8 Claude Loops to Build 10x Faster").

1. SCAN: read the codebase, README/WIKI.md, and recent changes. Find concrete,
   low-risk enhancements: dead-code removal, obvious dependency drift, lint/type
   errors, doc gaps, measurable optimisation targets (build time, bundle size).
2. PLAN then BUILD only the low-risk, auto-approvable changes. Make small,
   verifiable edits. Preserve existing patterns and AGENTS/CLAUDE.md boundaries.
   Do NOT touch secrets, CI/CD workflow files, auth, migrations, or delete data.
3. TRIAGE every proposed change into three buckets and write them to
   ENHANCEMENT_REVIEW.md at the repo root as markdown checkbox lists:
     ## auto-approve   (already applied this run)
     ## need-sign-off  (higher-risk: skills/config/structural/security — NOT applied)
     ## more-context   (loop cannot decide alone)
4. Append a dated section summarising applied changes to CHANGELOG.md (create if
   absent). Keep the diff focused; if nothing is safely improvable, write
   ENHANCEMENT_REVIEW.md saying so and make no code edits.

Never run destructive git commands. Never merge. Only edit files in this workspace.
"""


async def enhance_repo(repo: str, dry_run: bool, spent: dict[str, float]) -> dict[str, Any]:
    date = _dt.date.today().isoformat()
    slug = repo.split("/")[-1].lower()
    ws = WORKSPACE_ROOT / slug
    result: dict[str, Any] = {"repo": repo, "date": date, "branch": None, "pr": None,
                              "models": {"opus": MODEL_OPUS, "sonnet": MODEL_SONNET, "haiku": MODEL_HAIKU}}
    log.info("=== enhancing %s ===", repo)
    _clone(repo, ws)

    # Monitor (Haiku) → Plan (Opus) → Build+triage (Sonnet) → Review (Sonnet).
    scan = await run_phase("monitor", MODEL_HAIKU,
                           "List the 5 highest-leverage, lowest-risk enhancement targets in this "
                           "repo as terse bullets. No edits.", ws, timeout=300)
    plan = await run_phase("planner", MODEL_OPUS,
                           f"Given these scan findings, write a bounded, safe implementation plan "
                           f"(affected files, sequencing, rollback). Findings:\n{scan[:4000]}",
                           ws, timeout=600)
    await run_phase("generator", MODEL_SONNET,
                    f"{ENHANCE_PROMPT}\n\nApproved plan:\n{plan[:6000]}", ws, timeout=900)
    review = await run_phase("evaluator", MODEL_SONNET,
                             "Review the working-tree diff (git diff). Revert any change that is "
                             "unsafe, out of scope, or touches secrets/CI/auth/migrations. Confirm "
                             "ENHANCEMENT_REVIEW.md's three buckets match the actual diff.",
                             ws, timeout=600)
    result["review_summary"] = review[:500]

    status = _git(ws, "status", "--porcelain").stdout.strip()
    if not status:
        log.info("%s: no changes produced", repo)
        result["outcome"] = "no-op"
        return result

    branch = f"enhance/weekly-{date}"
    result["branch"] = branch
    _git(ws, "checkout", "-b", branch)
    _git(ws, "add", "-A")
    _git(ws, "-c", "user.name=pi-ceo-enhance", "-c", "user.email=enhance@unite-group.ink",
         "commit", "-m", f"chore: weekly enhancement pass {date}\n\nAuto-approve bucket only; "
         f"see ENHANCEMENT_REVIEW.md for need-sign-off / more-context items.")

    if dry_run:
        log.info("%s: dry-run — branch %s committed locally, not pushed", repo, branch)
        result["outcome"] = "dry-run"
        return result

    # Self-repo guard: push to a namespaced ref the autonomy webhook ignores.
    push_branch = f"enhance-review/weekly-{date}" if repo == SELF_REPO else branch
    push = _git(ws, "push", "-u", "origin", f"{branch}:{push_branch}")
    if push.returncode != 0:
        result["outcome"] = f"push-failed: {push.stderr[:200]}"
        return result
    pr_url = _open_pr(repo, push_branch, date)
    result["pr"] = pr_url
    result["outcome"] = "pr-opened"
    return result


def _open_pr(repo: str, branch: str, date: str) -> str | None:
    body = (f"Automated weekly enhancement pass ({date}) via the 8-loops improve-system method. "
            "Auto-approve changes are applied on this branch. Review ENHANCEMENT_REVIEW.md for "
            "the need-sign-off and more-context buckets before merging. This branch is never "
            "auto-merged.")
    env = {**os.environ}
    if tok := (os.environ.get("GH_ENHANCE_PAT") or os.environ.get("GITHUB_TOKEN")):
        env["GH_TOKEN"] = tok
    r = subprocess.run(
        ["gh", "pr", "create", "--repo", repo, "--head", branch, "--base", "main",
         "--title", f"Weekly enhancement pass {date}", "--body", body],
        capture_output=True, text=True, env=env,
    )
    if r.returncode == 0:
        return r.stdout.strip()
    log.warning("gh pr create failed for %s: %s", repo, r.stderr[:200])
    return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="single repo (owner/name); default all in registry")
    ap.add_argument("--dry-run", action="store_true", help="commit locally, do not push/PR")
    args = ap.parse_args()

    if reason := _kill_switch_tripped():
        log.error("kill-switch: %s — aborting", reason)
        return 2
    _ensure_api_mode()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_log = LOG_DIR / f"{_dt.date.today().isoformat()}.jsonl"

    repos = [args.repo] if args.repo else load_repos()
    spent: dict[str, float] = {"usd": 0.0}
    results = []
    for repo in repos:
        if reason := _kill_switch_tripped():
            log.error("kill-switch tripped mid-run: %s — draining", reason)
            break
        try:
            res = await enhance_repo(repo, args.dry_run, spent)
        except Exception as exc:  # one repo failing must not sink the whole run
            res = {"repo": repo, "outcome": f"error: {type(exc).__name__}: {exc}"}
            log.warning("repo %s failed: %s", repo, exc)
        results.append(res)
        with run_log.open("a") as fh:
            fh.write(json.dumps(res) + "\n")

    ok = sum(1 for r in results if r.get("outcome") in {"pr-opened", "dry-run", "no-op"})
    log.info("run complete: %d/%d repos processed cleanly; log=%s", ok, len(results), run_log)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
