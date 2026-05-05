---
name: tao-codebase-wiki
description: Self-updating per-directory WIKI.md files driven by post-merge git history. Port of @0xkobold/pi-codebase-wiki. Compounds: every merge refreshes context for the next TAO session.
---

# tao-codebase-wiki

Reads `git log <since>..HEAD --name-only`, groups commits by top-level
directory, and asks the SDK (sonnet, role=scribe) to refresh a compact
`<dir>/WIKI.md`. Token-budget guarded; kill-switch aware.

## When to trigger

- Post-merge GitHub Action (`.github/workflows/codebase-wiki.yml`).
- Ad-hoc CLI: `python scripts/run_codebase_wiki.py --since=<sha>`.
- Programmatic: `from app.server.tao_codebase_wiki import update_wiki`.

## Public API

```python
update_wiki(
    repo_root: str,
    since_ref: str | None = None,   # default: last-recorded SHA in WIKI.md or HEAD~50
    max_cost_usd: float = 0.02,     # per-directory budget
    dry_run: bool = False,
    directories: list[str] | None = None,
) -> WikiUpdateResult
```

`WikiUpdateResult` carries `directories_updated`, `files_written`,
`commits_summarized`, `cost_usd_estimate`, `bypassed`, `bypass_reason`.

## Budget knob

`max_cost_usd` defaults to $0.02 per directory. The GH Action sets
`TAO_MAX_COST_USD=0.05` so a single merge can refresh several directories.

## Kill-switch integration

`LoopCounter.tick()` runs at the start of each directory iteration. A
`TAO_HARD_STOP_FILE` causes a graceful bypass (`bypass_reason=kill_switch:HARD_STOP`).
