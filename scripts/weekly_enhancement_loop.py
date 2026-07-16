#!/usr/bin/env python3
"""Weekly cross-repo enhancement loop (8-Claude-Loops improve-system method).

Runs every Monday 02:00 AEST. For every repo in .harness/projects.json it clones
an isolated workspace and runs an improve-system pass through the Opus/Sonnet/Haiku
model ladder, then opens a review PR (never merges). See
skills/weekly-enhancement-loop/SKILL.md and
docs/sources/8-claude-loops-to-build-10x-faster.md.

Model ladder runs on OpenRouter (Anthropic Messages API surface). Fable-5 left
the Max plan 2026-07-08 and the direct Anthropic org has no API credit, so this
loop bills OpenRouter credit. Founder directive 2026-07-05: push the grunt tiers
onto cheap open-weight models and reserve a single stronger open-weight reasoner
for the planner handoff — the only critical-call checkpoint. This cuts the run
from ~$8/repo (Opus/Sonnet/Haiku) to ~$0.4/repo:

    planner  (handoff/decision)  -> ENHANCE_MODEL_HANDOFF (deepseek/deepseek-v4-pro)
    generator (build grunt)      -> ENHANCE_MODEL_BUILD   (qwen/qwen3-coder-30b-a3b-instruct)
    evaluator (review grunt)     -> ENHANCE_MODEL_REVIEW  (deepseek/deepseek-v4-flash)
    monitor  (scan grunt)        -> ENHANCE_MODEL_SCAN    (qwen/qwen3-235b-a22b-2507)

OpenRouter's /v1/messages endpoint speaks native Anthropic tool-use (it routes
open-weight models through the same tool_use / usage.cost schema), so this file
is a self-contained tool-use agent (read_file / write_file / list_dir / run_bash,
all scoped to the cloned workspace). No Claude Code CLI, no claude_agent_sdk —
the CLI rejects OpenRouter slash-slugs, so the agent loop lives here.

Abort axes (shared with every TAO loop, RA-1966): TAO_HARD_STOP_FILE,
TAO_MAX_COST_USD (real spend from OpenRouter usage.cost), and a per-phase
iteration cap. Nothing is merged to main; each repo yields at most one open PR per
week on branch enhance/weekly-<date>.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weekly-enhancement-loop")

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / ".harness" / "projects.json"
LOG_DIR = REPO_ROOT / ".harness" / "enhancement-loop"
WORKSPACE_ROOT = Path(os.environ.get("ENHANCE_WORKSPACE", "/tmp/pi-ceo-enhance"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Role-based ladder (founder directive 2026-07-05): cheap open-weight models for
# the grunt tiers, one stronger open-weight reasoner reserved for the planner
# handoff. No Anthropic premium model is used — the RA-1099 spirit ("never spend a
# premium model on scan/build") is honoured absolutely. Override any slug via env.
MODEL_HANDOFF = os.environ.get("ENHANCE_MODEL_HANDOFF", "deepseek/deepseek-v4-pro")
MODEL_BUILD = os.environ.get("ENHANCE_MODEL_BUILD", "qwen/qwen3-coder-30b-a3b-instruct")
MODEL_REVIEW = os.environ.get("ENHANCE_MODEL_REVIEW", "deepseek/deepseek-v4-flash")
MODEL_SCAN = os.environ.get("ENHANCE_MODEL_SCAN", "qwen/qwen3-235b-a22b-2507")

HARD_STOP_FILE = Path(os.environ.get("TAO_HARD_STOP_FILE", str(Path.home() / ".claude" / "HARD_STOP")))
MAX_COST_USD = float(os.environ.get("TAO_MAX_COST_USD", "5.00"))
# Per-phase cap on tool-use round-trips — bounds a runaway agent even before the
# dollar ceiling trips (RA-1966 TAO_MAX_ITERS analogue).
MAX_PHASE_ITERS = int(os.environ.get("ENHANCE_MAX_PHASE_ITERS", "40"))
# The loop's self-repo — enhancing it is allowed but must never push a ref the
# autonomy webhook re-triggers on (RA-1182: 43 zombie branches).
SELF_REPO = "CleanExpo/Pi-Dev-Ops"


class CostCeilingHit(RuntimeError):
    """Raised when accumulated OpenRouter spend crosses TAO_MAX_COST_USD."""


def _kill_switch_tripped() -> str | None:
    if HARD_STOP_FILE.exists():
        return f"hard-stop file present: {HARD_STOP_FILE}"
    return None


def load_repos() -> list[str]:
    data = json.loads(REGISTRY.read_text())
    return sorted({p["repo"] for p in data["projects"]})


def _openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "OPENROUTER_API_KEY missing. This loop bills OpenRouter credit (the "
            "direct Anthropic org has no API credit and Fable-5 left the Max plan "
            "2026-07-08). Set it as an Actions secret or in "
            "~/.config/piceo/enhancement.env."
        )
    return key


# --- Tool implementations (all scoped to the cloned workspace) ---------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file relative to the repo root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file relative to the repo root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_dir",
        "description": "List entries in a directory relative to the repo root (default '.').",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
    {
        "name": "run_bash",
        "description": "Run a shell command in the repo root. Use for git diff/status, grep, "
        "build/lint/type checks. Never run destructive or network-mutating commands.",
        "input_schema": {
            "type": "object",
            "properties": {"cmd": {"type": "string"}},
            "required": ["cmd"],
        },
    },
]


def _resolve(cwd: Path, rel: str) -> Path:
    """Resolve rel against cwd, refusing to escape the workspace.

    Resolve the base too — on macOS /tmp and mkdtemp go through a /private
    symlink, so comparing an unresolved cwd against a resolved target would
    wrongly reject in-workspace paths.
    """
    base = cwd.resolve()
    target = (base / rel).resolve()
    if base not in target.parents and target != base:
        raise ValueError(f"path escapes workspace: {rel}")
    return target


def _exec_tool(name: str, args: dict[str, Any], cwd: Path) -> str:
    try:
        if name == "read_file":
            p = _resolve(cwd, args["path"])
            if not p.is_file():
                return f"ERROR: not a file: {args['path']}"
            return p.read_text(encoding="utf-8", errors="replace")[:60000]
        if name == "write_file":
            p = _resolve(cwd, args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8")
            return f"wrote {len(args['content'])} bytes to {args['path']}"
        if name == "list_dir":
            p = _resolve(cwd, args.get("path", "."))
            if not p.is_dir():
                return f"ERROR: not a dir: {args.get('path', '.')}"
            return "\n".join(sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir()))[:20000]
        if name == "run_bash":
            r = subprocess.run(
                ["bash", "-lc", args["cmd"]], cwd=str(cwd),
                capture_output=True, text=True, timeout=300,
            )
            out = (r.stdout + r.stderr)[:30000]
            return f"exit={r.returncode}\n{out}"
        return f"ERROR: unknown tool {name}"
    except Exception as exc:  # tool errors are fed back to the model, not fatal
        return f"ERROR: {type(exc).__name__}: {exc}"


def _post(payload: dict[str, Any], key: str, timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        OPENROUTER_URL, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
            "HTTP-Referer": "https://github.com/CleanExpo/Pi-Dev-Ops",
            "X-Title": "weekly-enhancement-loop",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def run_phase(role: str, model: str, prompt: str, cwd: Path, timeout: int,
              spent: dict[str, float]) -> str:
    """One agentic phase: native Anthropic tool-use loop over OpenRouter.

    Loops model <-> tools until the model stops requesting tools, the per-phase
    iteration cap is hit, or the dollar ceiling trips (CostCeilingHit).
    """
    key = _openrouter_key()
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    text_out: list[str] = []
    t0 = time.monotonic()

    for _ in range(MAX_PHASE_ITERS):
        if reason := _kill_switch_tripped():
            raise CostCeilingHit(f"kill-switch during phase {role}: {reason}")
        payload = {
            "model": model,
            "max_tokens": 8000,
            "usage": {"include": True},
            "tools": TOOLS,
            "messages": messages,
        }
        resp = _post(payload, key, timeout)
        spent["usd"] += float(resp.get("usage", {}).get("cost", 0.0) or 0.0)
        if spent["usd"] >= MAX_COST_USD:
            raise CostCeilingHit(f"spend ${spent['usd']:.4f} >= cap ${MAX_COST_USD:.2f}")

        content = resp.get("content", [])
        messages.append({"role": "assistant", "content": content})
        tool_results = []
        for block in content:
            if block.get("type") == "text":
                text_out.append(block["text"])
            elif block.get("type") == "tool_use":
                out = _exec_tool(block["name"], block.get("input", {}), cwd)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": out,
                })
        if resp.get("stop_reason") != "tool_use":
            break
        messages.append({"role": "user", "content": tool_results})

    log.info("phase %s (%s) done in %.1fs; run spend $%.4f",
             role, model, time.monotonic() - t0, spent["usd"])
    return "\n".join(text_out)


def _clone(repo: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GH_ENHANCE_PAT") or os.environ.get("GITHUB_TOKEN", "")
    url = f"https://x-access-token:{token}@github.com/{repo}.git" if token else f"https://github.com/{repo}.git"
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True, capture_output=True)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


ENHANCE_PROMPT = """You are the weekly enhancement loop for the repo checked out at the current
working directory. Apply the improve-system method (loops 4-8 of
"8 Claude Loops to Build 10x Faster"). Use the read_file/write_file/list_dir/run_bash
tools to inspect and edit files; run git diff/status to check your own work.

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


def enhance_repo(repo: str, dry_run: bool, spent: dict[str, float]) -> dict[str, Any]:
    date = _dt.date.today().isoformat()
    slug = repo.split("/")[-1].lower()
    ws = WORKSPACE_ROOT / slug
    result: dict[str, Any] = {"repo": repo, "date": date, "branch": None, "pr": None,
                              "models": {"handoff": MODEL_HANDOFF, "build": MODEL_BUILD,
                                         "review": MODEL_REVIEW, "scan": MODEL_SCAN}}
    log.info("=== enhancing %s ===", repo)
    _clone(repo, ws)

    # Scan (grunt) → Plan (handoff/decision) → Build (grunt) → Review (grunt).
    scan = run_phase("monitor", MODEL_SCAN,
                     "List the 5 highest-leverage, lowest-risk enhancement targets in this "
                     "repo as terse bullets. Read files as needed. Make no edits.",
                     ws, timeout=300, spent=spent)
    plan = run_phase("planner", MODEL_HANDOFF,
                     f"Given these scan findings, write a bounded, safe implementation plan "
                     f"(affected files, sequencing, rollback). Findings:\n{scan[:4000]}",
                     ws, timeout=600, spent=spent)
    run_phase("generator", MODEL_BUILD,
              f"{ENHANCE_PROMPT}\n\nApproved plan:\n{plan[:6000]}", ws, timeout=900, spent=spent)
    review = run_phase("evaluator", MODEL_REVIEW,
                       "Review the working-tree diff (run `git diff`). Revert any change that is "
                       "unsafe, out of scope, or touches secrets/CI/auth/migrations. Confirm "
                       "ENHANCEMENT_REVIEW.md's three buckets match the actual diff.",
                       ws, timeout=600, spent=spent)
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="single repo (owner/name); default all in registry")
    ap.add_argument("--dry-run", action="store_true", help="commit locally, do not push/PR")
    args = ap.parse_args()

    if reason := _kill_switch_tripped():
        log.error("kill-switch: %s — aborting", reason)
        return 2
    _openrouter_key()  # fail fast if the credential is absent
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
            res = enhance_repo(repo, args.dry_run, spent)
        except CostCeilingHit as exc:
            log.error("cost/kill ceiling hit: %s — draining run", exc)
            results.append({"repo": repo, "outcome": f"aborted: {exc}"})
            break
        except Exception as exc:  # one repo failing must not sink the whole run
            res = {"repo": repo, "outcome": f"error: {type(exc).__name__}: {exc}"}
            log.warning("repo %s failed: %s", repo, exc)
        else:
            res["spend_usd"] = round(spent["usd"], 4)
        results.append(res)
        with run_log.open("a") as fh:
            fh.write(json.dumps(res) + "\n")

    ok = sum(1 for r in results if r.get("outcome") in {"pr-opened", "dry-run", "no-op"})
    log.info("run complete: %d/%d repos processed cleanly; spend $%.4f; log=%s",
             ok, len(results), spent["usd"], run_log)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
