# QUEUE

Read by the `keep-going.sh` Stop hook (`~/.claude/hooks/keep-going.sh`). While any
`- [ ]` item remains here, the hook blocks the session from ending and pushes the next
item. Draining the queue is what makes the terminal continue without re-prompting.

**Rule:** only genuinely actionable items go under Active. Anything waiting on a person
or an external system goes under BLOCKED with a different marker — an unchecked item that
cannot be completed turns the Stop hook into an unsatisfiable loop, which is the failure
mode `goal-circuit-breaker` exists to catch.

## Active

- [ ] Reproduce CI's `smoke-local` job locally — the one CI job not yet covered. It starts
      the server on 127.0.0.1:7777 with a dummy password and runs
      `scripts/smoke_test.py --url ... --password ...`. `handoff-loop.sh`'s `audit-smoke`
      gate SKIPs when nothing is listening on :7777, which means the repo's end-to-end
      surface check has been silently skipped every run. Run it for real and record the
      result; if it passes, consider whether the gate should start its own server rather
      than SKIP.

## BLOCKED — founder action, do not treat as queue items

* **GitHub Actions allocates no runner** (since 2026-08-14T05:20Z). Needs a billing or
  infrastructure decision. Evidence and the three options:
  `docs/BLOCKER-github-actions-runners-2026-08-18.md`.
* **Mission Control authenticated payload unverified.** No `.env.local` on this machine,
  so `scripts/smoke_test.py` cannot authenticate. Every protected endpoint correctly
  returns 401 and `/control` 307s to login; the surfaces are up, the payload content is
  unconfirmed.

## Done — 2026-08-18 overnight

- [x] `secrets_check.py` reported 102 vendored files as exposed secrets on every local run
      (`.venv-verify/` missed by a name-based filter) and rewrote `.gitignore`. Fixed by
      matching `site-packages/` structurally, with a verified NOT_COMMITTED precondition.
- [x] Second defect found by those tests: `_list_tracked_files() or _list_all_files()`
      treated "everything filtered" as "git unavailable" and re-walked the tree.
- [x] CLAUDE.md pointed four references at `.harness/projects.json`, which no longer exists.
- [x] Registry carried no `vercel_project_id`, so the RA-1742 check inspected nothing;
      wired 4 ids and corrected two stale frontend URLs (one was a 404 used by two entries).
- [x] Diagnosed and documented the Actions runner starvation.
- [x] `handoff-loop.sh` was weaker than the CI job it stands in for: it excluded
      `test_sdk_phase2.py` on a stale "CI-only" premise, and ran neither `pytest swarm/`
      nor `check_provisioning.py`. All three closed — it is now the CI-parity runner, so
      no second `ci_local.sh` is needed.
- [x] `agentskills.json/yaml` had drifted (b881b4e0 added `agent-browser` without
      regenerating; `boardroom` + `nexus` hashes stale). Regenerated. Confirmed the gate is
      passable rather than permanently red: two consecutive runs are byte-identical.
- [x] Vercel `ignoreCommand` — DECISION: deliberately deferred, not skipped. Groundwork
      done: `dashboard/package.json` has no local path dependencies (so no `packages/`
      change can affect the build, which was the trap that would have made a naive
      `dashboard/`-scoped check silently serve stale UI), rootDirectory is `dashboard`,
      and `git diff --quiet HEAD^ HEAD .` is the correct command. Not applied, because it
      changes production deployment behaviour, its failure mode is a build skipped when it
      should have run, and it cannot be validated while no push to `main` is happening and
      Actions allocates no runner. Low-value efficiency work is not worth an unverifiable
      production change. Apply and watch one deploy once runners return.
      The original premise — five `BLOCKED` deploys blamed on the wiki bot — was wrong and
      is disproven: all five fall between 03:59 and 05:20 on 2026-08-14, the latest
      deployment is `READY`, and no push to `main` has happened since.
- [x] `.venv-verify/` — premise was wrong, no code change needed. `.gitignore:163`
      (`.venv*/`) already covers it, confirmed via `git check-ignore -v`, so it was never
      a git risk. It reached the secrets scan only because that scanner deliberately drops
      `--exclude-standard` in order to see `.env.local` / `*.pem`; the `site-packages/`
      fix already excludes it. Nothing in the repo creates or references it. It is a stray
      303 MB local artifact — deleting 8,099 files is Phill's call, not an agent's, and it
      now costs nothing to leave in place.
- [x] `secrets_check.py` `.gitignore` write — DECISION: no change. The split is already
      coherent and deliberate: default = detect *and* remediate, `--dry-run` = measure
      only, documented at `secrets_check.py:70`. `handoff-loop.sh` correctly uses
      `--dry-run` on the stated principle that "a gate must measure, not act", and CI uses
      the default where mutation is harmless in a fresh checkout and the exit code is what
      blocks the merge. Moving the write behind a `--fix` flag would be unrequested
      refactoring of working, documented behaviour.
- [x] `/health` verified END-TO-END against a running local server, not just read from
      source: the authed payload carries `linear_api_key`, `github_token`, `vercel_token`
      and `autonomy.{enabled,armed,poll_count,last_tick,seconds_since_last_poll}`. The
      CLAUDE.md requirement is already met; unauthed correctly returns `{"status":"ok"}`.
