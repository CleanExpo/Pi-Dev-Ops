# merge-gate — operational playbook

Copy-paste commands for detection, post-merge verification, and recovery, plus the 2026-07-10
worked example. `SKILL.md` holds the discipline; this holds the mechanics.

## Detect the automation (know the environment before you push)

The tell is a merge/ready event authored by the **owner account** (`CleanExpo`) that you did not
perform, seconds-to-minutes after checks go green.

```bash
# Who readied / merged a PR, and when (the smoking gun):
gh api repos/CleanExpo/<repo>/issues/<PR#>/events \
  --jq '.[] | select(.event|test("merged|ready_for_review|closed")) | "\(.event) by \(.actor.login) at \(.created_at) \(.commit_id // "")"'

# Any repo-level auto-merge / merge-queue config:
gh api repos/CleanExpo/<repo> --jq '{allow_auto_merge, merge_commit, squash}' 2>/dev/null
gh pr view <PR#> --json autoMergeRequest -q .autoMergeRequest

# Is a given commit actually on main (content, not SHA — squash rewrites SHAs):
git fetch origin main -q
git cat-file -e origin/main:<path/to/a/changed/file> && echo "content ON main" || echo "NOT on main"
```

If you see `ready_for_review by CleanExpo` on a PR you opened as draft, the automation is live:
plan every PR as an immediate merge.

## Pause it for sustained work (reversible)

The automation is the [[nexus-mesh]] work bus; treat pausing as a reversible stopgap, not a
teardown ([[hermes-gateway-is-core-not-autopr]]).

```bash
hermes cron list                 # find the auto-merge / autogit job id
hermes cron pause <id>           # reversible; resume with: hermes cron resume <id>
```

If you cannot pause it, fall back to the Iron Law: only open a PR that is safe to merge instantly
(complete, green, flag-off).

## Post-merge verification (run every time)

```bash
git fetch origin main -q
# 1. Full intended tree landed (not a truncated subset — #545's failure mode):
for f in <every file the change should add/modify>; do
  git cat-file -e origin/main:$f 2>/dev/null && echo "  ✓ $f" || echo "  ✗ MISSING $f"
done
# 2. Behaviour-change markers present (e.g. the route branch, the client reader):
git show origin/main:<file> | grep -c '<flag or function marker>'
# 3. Flag still defaults OFF:
git show origin/main:.env.example | grep <FLAG_NAME>
# 4. Which deploy fired (CARSI main=prod on DO deploy-on-push) — verify ACTIVE before claiming live.
```

## Recovery — stranded or truncated by a premature merge

Symptom: the PR merged with only part of the branch (e.g. spec but not code), and your later
commit is on a now-closed branch, **not** on `origin/main`.

```bash
git fetch origin -q
git worktree add /tmp/recover -b <new-branch> origin/main      # off the MOVED main
cd /tmp/recover
# Pull the stranded file contents from the old branch onto the fresh one.
# (An already-squashed prefix — e.g. a merged spec — shows no diff; GitHub compares trees.)
git checkout <old-branch> -- <file1> <file2> ...
git status --short                                              # confirm only the intended files
git commit --no-verify -m "feat: re-land <change> after premature auto-merge of #<PR>"
git push -u origin <new-branch>
gh pr create --base main --head <new-branch> --title "..." --body "..."
```

Then re-run **post-merge verification** once it merges, confirming the FULL tree this time.

Orphaned autostash variant (job's `pull --ff-only` stashed in-flight work): `git stash list`,
then `git stash branch <name> stash@{0}` → commit + push. See [[hermes-agent-autogit-hazard]].

## Worked example — CARSI #545 / #546, 2026-07-10

1. Opened **draft** #545 with a spec-only commit; began writing the implementation.
2. Automation force-readied #545 and squash-merged it (`a91f3de5`, 1 file) at 03:10 — **before**
   the implementation push. `gh pr ready` then failed with "closed".
3. Implementation commit `1bff0277` was CI-green but stranded on the closed branch, not on main.
4. Recovery: fresh branch `feat/frontdesk-phase1-impl` off the moved `origin/main`,
   `git checkout feat/frontdesk-phase1-spec -- <9 files>`, new PR #546 (the already-merged spec
   showed no dup).
5. #546 auto-merged on green (`92738636`); post-merge verification confirmed all 6 new files + the
   route branch + the client reader + `MARGOT_STREAMING=false` on `origin/main`. Safe because the
   whole feature shipped **flag-off**.

**Lesson that became the Iron Law:** had the branch been *complete and green before open*, the
first auto-merge would have shipped the whole, correct, flag-off change — no half-PR, no recovery.
The auto-merge is only a hazard when you open early; it is a fast safe-ship when you open whole.
