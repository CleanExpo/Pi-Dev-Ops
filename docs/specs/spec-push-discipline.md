# SPM Spec — Fix the Push/Merge Regression Loop

_Status: DRAFT for approval · Author: Pi (SPM) · 2026-07-01 · Repo: CleanExpo/Pi-Dev-Ops_

## 1. Task
Stop the recurring "green PR, then the next PR is red again" regression on `CleanExpo/Pi-Dev-Ops`.
The user's words: "#440 merge issues… you have gone backwards… fix this issue we are having with push commands."

## 2. Project context
Pi-Dev-Ops has multiple concurrent writers to one repo: (a) feature-branch PRs, (b) an autogit
workbus that commits/pushes every turn, (c) a live Codex/Cursor session, (d) GitHub Actions that
push `docs(wiki)` commits with `[skip ci]`, (e) daily harness routines that write `.harness/` state.

## 3. Problem statement (evidence-backed)
`main`'s branch protection is effectively disabled, so broken code reaches `main` untested and
every branch cut from `main` inherits the breakage. Four confirmed root causes:

- **RC1 — Protection is off.** `gh api …/branches/main/protection`: `required_status_checks.checks = []`
  (no check is actually required), `enforce_admins = false` (admins/Codex bypass all rules),
  `restrictions = null` (direct pushes to `main` allowed). CI is advisory, not a gate.
- **RC2 — Untested commits land on `main`.** History shows raw chat prompts committed straight to
  `main`: `e64f6463 "Whats next?"` and `520935f7 "lets build it"` each have **0 check-runs**
  (`gh api …/commits/<sha>/check-runs`). `b45da6aa` ("Pull all required from the Vercel Environment")
  introduced the ruff F401 breakage AND the two-label autonomy loop directly on `main`.
- **RC3 — The fix can't reach `main`.** The ruff fix for `boardroom.py`/`storm_evidence.py` lives on
  the unmerged #439 branch. #440 was cut from the still-broken `main`, so its CI re-fails on the
  same two F401s (`boardroom.py:10`, `storm_evidence.py:8`) plus 5 of its own
  (`config.py:189-192`, `pipeline.py:246`). Fixing one PR never fixes `main` → next PR red again.
- **RC4 — Tracked harness runtime state.** `.harness/portfolio-pulse/**` and `.harness/cron-triggers.json`
  are NOT gitignored (`git check-ignore` returns blank), so autogit + daily routines commit "today's"
  versions on every branch → the 9 add/add + content conflicts seen resolving #439, recurring per PR.

## 4. Desired outcome
`main` is always green. A push containing failing ruff/pytest/tsc cannot reach `main`. Routine
`.harness/` churn never causes merge conflicts. Autonomous push paths keep working.

## 5. Scope / non-goals
- **In scope:** branch-protection config; `.gitignore` for harness runtime state; landing the ruff fix
  on `main`; a local pre-push gate; writer-coordination rule.
- **Non-goals:** rewriting the autogit workbus; changing CI test content; touching product features in #440.

## 6. Existing capability (reuse, don't rebuild)
- `scripts/handoff-loop.sh` already runs the definition-of-done gates (clean→deps→type→lint→tests→build).
  Reuse it as the pre-push gate rather than inventing a new one.
- CI job `Python (pytest + ruff)` already exists and passes when code is clean — it just isn't *required*.
- `.harness/swarm/botfather_queue.jsonl` is already gitignored — the correct pattern to extend to the
  other runtime files.

## 7. Specialist board
- **Architect:** the defect is governance, not code — enforce the gate that already exists; don't add machinery.
- **Security:** `enforce_admins=false` means any admin token (Codex) writes unreviewed to `main`; close it,
  but allow-list the automation identity so autonomous flows survive.
- **QA:** make `Python (pytest + ruff)` a *required* check; a required check that can't be bypassed is the
  whole fix for RC1/RC2.
- **Devil's advocate:** locking `main` will break the wiki-refresh Action and autogit if they push directly to
  `main`. That tension is the one real decision (see §8).

## 8. Judge challenge — the one genuine decision
Hardening `main` (require PR + required checks + enforce_admins) will block the automation that currently
pushes straight to `main` (codebase-wiki `[skip ci]` commits; possibly autogit). Two coherent options:

- **A. Lock hard, allow-list automation (recommended).** Require the CI check, `enforce_admins=true`,
  require-PR-before-merge, and add the Actions/automation identity to the push allowlist. Humans + Codex
  go through green PRs; bots keep direct access. Strongest guarantee; needs the automation identity named.
- **B. Lock merges only.** Set required checks + strict, leave direct push open. Stops red *PR merges* but
  NOT the raw-prompt direct-to-main pushes (RC2 persists). Weaker; lower blast radius on automation.

Score: A = 92/100 (APPROVE BUILD), B = 70/100 (REDUCE SCOPE — leaves RC2 open). Recommendation: **A**.

## 9. Proposed solution
1. **Land the ruff fix on `main` (unblock today).** Merge #439 (green, mergeable) or cherry-pick its
   `fix(spec_pipeline)` commit to `main`. #440 then rebases onto a green `main` and only needs its own
   5 F401s fixed.
2. **Make CI a required check (RC1/RC2).** Add `Python (pytest + ruff)` and `Frontend (tsc + eslint + build)`
   to `required_status_checks.checks`; set `enforce_admins=true`; require a PR before merge.
3. **Allow-list automation (Option A).** Add the wiki/autogit bot identity to the push restriction allowlist
   so `[skip ci]` doc pushes and the workbus keep functioning.
4. **Gitignore harness runtime state (RC4).** Add `.harness/portfolio-pulse/`, `.harness/cron-triggers.json`,
   and sibling runtime files to `.gitignore`; `git rm --cached` them. Kills the recurring conflict class.
5. **Pre-push gate (defense in depth).** A `pre-push` hook (or CONTRIBUTING rule) that runs
   `scripts/handoff-loop.sh` — ruff + pytest must pass locally before any push.
6. **Writer coordination (RC4/RC3).** Codex/Cursor works on its own `feature/*` branch; autogit must not
   push to a branch a Codex session owns. Document the one-writer-per-branch rule in CLAUDE.md.

## 10. UX requirements
Not a UI change. Developer-facing: a blocked push must state which gate failed (ruff/pytest) and the exact
file:line — `handoff-loop.sh` already does this.

## 11. Technical requirements
- Branch-protection change via `gh api -X PUT repos/CleanExpo/Pi-Dev-Ops/branches/main/protection` with the
  full protection payload (GitHub requires all fields on PUT).
- `.gitignore` additions + `git rm -r --cached .harness/portfolio-pulse .harness/cron-triggers.json`.
- Exact required-check *names* must match the check-run names GitHub sees
  (`Python (pytest + ruff)`, `Frontend (tsc + eslint + build)`).

## 12. Security / privacy
Closing `enforce_admins` removes the unreviewed-write path to `main`. The automation allowlist must name a
least-privilege identity (the Actions `GITHUB_TOKEN` / dedicated bot), not a personal admin PAT.

## 13. Verification plan
- After §9.2/§9.3: `gh api …/branches/main/protection` shows non-empty `required_checks`, `enforce_admins=true`.
- Attempt a trivial direct push to `main` as a non-allowlisted identity → rejected.
- Open a throwaway PR with a deliberate F401 → merge blocked until fixed.
- After §9.4: `git check-ignore .harness/portfolio-pulse/x.md` returns the path; a daily routine run produces
  no `git status` churn on tracked files.

## 14. Loop / stress testing
- Cut 3 successive branches from `main`, each running `handoff-loop.sh` pre-push; confirm none inherit a red
  `main`. Run the daily portfolio-pulse routine on two branches simultaneously; confirm zero merge conflicts.

## 15. Acceptance criteria
- [ ] `main` CI (`Python (pytest + ruff)`) is green and the two F401 files are fixed on `main`.
- [ ] `required_status_checks.checks` is non-empty; `enforce_admins=true`; PR-before-merge on.
- [ ] Automation identity allow-listed; wiki `[skip ci]` push still succeeds.
- [ ] `.harness/portfolio-pulse/**` + `cron-triggers.json` gitignored and `--cached`-removed.
- [ ] A PR with a lint/test failure cannot be merged; a clean PR can.

## 16. Goal command
```text
/goal Harden CleanExpo/Pi-Dev-Ops push discipline so main is always green:
(1) land the #439 ruff fix on main; (2) add .harness/portfolio-pulse/ + .harness/cron-triggers.json
to .gitignore and git rm --cached them; (3) set branch protection on main — required checks
["Python (pytest + ruff)","Frontend (tsc + eslint + build)"], enforce_admins=true, require PR before
merge, allow-list the automation bot; (4) add a pre-push hook running scripts/handoff-loop.sh.
Done when: main CI green, a deliberately-red PR is merge-blocked, a clean PR merges, and a daily
routine run produces no tracked-file churn.
```

## 17. Implementation sequence
1. Land ruff fix on `main` (merge #439 or cherry-pick) — unblocks #440 immediately.
2. Gitignore + `git rm --cached` harness runtime files (one small PR).
3. PUT branch-protection config (required checks + enforce_admins + PR-required + bot allowlist).
4. Add `pre-push` hook + CLAUDE.md one-writer-per-branch rule.
5. Rebase #440 on green `main`, fix its 5 own F401s, verify green.

## 18. Session-handoff seed
Root cause = disabled branch protection (`required_checks:[]`, `enforce_admins:false`, `restrict:false`)
letting untested/direct pushes break `main`; fix is governance + gitignore + landing the stuck ruff fix,
not code. #439 is green/mergeable and carries the ruff fix. #440 red on the same F401 class + 5 own.

## 19. Final recommendation
**APPROVE BUILD (Option A), 92/100.** The regression is a governance hole, not a coding bug: the gate that
would have caught every one of these failures exists but is not enforced. Turn it on, allow-list the bots,
gitignore the routine churn, and land the one stuck fix. Highest-leverage first move: land the #439 ruff
fix on `main` so #440 stops inheriting a broken tree.
