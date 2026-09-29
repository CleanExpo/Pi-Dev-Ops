---
name: shipyard
description: Overnight start-to-finish runner. Takes queued work (finish a PR, finish a branch, build a spec) through worktree, build, gates, mutation control, independent review, release receipt, push and draft PR, and stops at merge-ready with a morning report. Use for "run overnight", "clear the shelf", "ship the backlog", "/shipyard".
updated: 2026-09-17
---

# Shipyard: spec to merge-ready, without stopping

The founder merges. Everything before the merge is this skill's job.

## Files

| Path | What |
|---|---|
| `~/.local/state/shipyard/queue.json` | the work items, in order |
| `~/.local/state/shipyard/repos/<repo>.json` | per-repo `node`, `gates`, `ci_parity`, `review_lane`, `pr_base`, `notes` |
| `~/.local/state/shipyard/logs/` | every gate log, named `<item>-<command>.log` |
| `~/.claude/skills/pr-release-gate/scripts/independent_review.py` | review lanes: cursor, codex, gemini, openrouter (in that order) |
| `~/.claude/skills/pr-release-gate/scripts/rereview.sh` | provision + direct Cursor review in a worktree |

Queue item: `{id, repo, kind: finish-pr|finish-branch|build-spec, ref, status, max_review_rounds (default 3), rounds, note, parked_reason}`.
Status moves `queued → building → reviewing → merge-ready` or `→ parked`.

## The loop

**Read `references/autonomous-run-contract.md` first.** It sets the decision classes (decide
Mechanical and Taste items without asking; save Taste items for one final gate), the four finish
statuses, the three-strikes rule, stage handoff files, and the mandatory learnings step.

Run in one session, in `/loop` dynamic mode. Up to 3 items are in flight at once.
**Waiting is not stopping.** While a review or CI runs, start the next queued item. Background-task notifications wake the loop. `ScheduleWakeup` 1200s is only the fallback.

Per item, each stage has an exit check. An item never advances on a claim, only on the check.

1. **Contract**: `donectl start` / `lock` with the item's done-when commands.
2. **Worktree**: a new worktree per item, off fresh `origin/<pr_base>` (or on the PR head for finish-pr). Never build in the main checkout.
3. **Spec**: `build-spec` only. `/spm`, then `/bench`, and `engineering_gate.py` must exit 0.
4. **Build**: a background builder agent. Its prompt carries the hard rules below and asks for: head SHA, merge-base, each gate with its exit code.
5. **Gates**: every `gates` + `ci_parity` command on the exact commit, with the repo's Node version. Logs are saved.
6. **Mutation control**: break the new guard or test once, watch it fail, restore byte-identical.
7. **Review**: a detached review worktree at the head SHA. The brief names base and head SHAs, the diff scope, the drain list and the report contract. Run `independent_review.py --lane cursor ...` or `rereview.sh`. Judge the report file, never the exit code.
8. **Fix loop**: on FAIL, fix, then back to 5. **Max `max_review_rounds` (3).** Then park the item with the findings and move on.
9. **Receipt**: `pr_release_gate.py issue --primary-agent claude --review-report <abs> --test ...`, then `verify`.
10. **Push + draft PR**: plain `git push -u origin <branch>` from the worktree cwd. `gh pr create --draft --body-file <file>` from the repo cwd.
11. **Ready**: `gh pr ready` only when every CI check is green. Otherwise go back to 5 with the CI log. Park after two identical CI failures.
12. **Report**: add a row to the morning report, with the item's contract status (`DONE`,
    `DONE_WITH_CONCERNS`, `BLOCKED` or `NEEDS_CONTEXT`) and its evidence.

## Parking (the stop rule that keeps the loop moving)

Park an item, write the reason in `parked_reason`, and move on when any of these holds:
- the review-round cap is hit (the CARSI IICRC guard ran 16 rounds on 17/09; never again);
- it needs a founder-only thing: key, vendor, spend, merge, prod DB, deletion, or a direction choice;
- two identical failures, after a `guard.py hypothesis` was recorded.

Never re-describe a parked item on the next wake. Parked is terminal until the founder acts.

## Hard rules (copy into every builder prompt)

- No `--no-verify`, no force push, no `PR_RELEASE_GATE_HUMAN_OVERRIDE`, no rebase of a pushed branch (merge `origin/main` instead).
- No `gh pr merge`, no deploys, no production DB writes, no secret reads or prints, no new vendors or dependencies without a founder note.
- Never weaken a guard, raise a warning cap, or add skip / ignore / disable to pass a gate.
- Never edit a reviewer report. Never delete branches or worktrees.
- gh runs from the repo cwd, never with `--repo`. No multiline or `$(...)` git/gh commands. Write bodies to files first.
- Prompt-free command shapes: redirect logs only to `~/.local/state/shipyard/logs/*.log`; never `cd … &&` a reader, never two `cd`s in one command; no `rm -rf`, no `git worktree remove`; never name `.env*` (except `.env.example`), `.pem` or key files.

## Morning report

One Artifact page, with rows from `queue.json` and real links and SHAs only:
1. **Merge-ready**: PR, head SHA, gates passed, review verdict and lane.
2. **Parked**: the reason and the exact next step.
3. **Needs you**: keys, vendors, merges, cleanup (deletions are listed, never done).
4. **Decisions made for you**: every Taste and User-challenge item from the run, with the choice
   and what was rejected. This is the single final gate.
5. **Learnings**: what was saved to memory, or "No durable learnings this run".

## Known lane facts (check, don't trust)

- Cursor is lane 1 (added 17/09). Codex exits 0 on quota with no report. Gemini reports were rejected for lacking mutation evidence.
- A FAIL with zero blocking findings is not a review. The runner falls through to the next lane.
- A `~/.claude` branch with a huge diff cannot be receipt-cleared. Those changes stay local, and the morning report says so.
