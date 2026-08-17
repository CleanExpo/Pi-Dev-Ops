# QUEUE

Read by the `keep-going.sh` Stop hook (`~/.claude/hooks/keep-going.sh`). While any
`- [ ]` item remains here, the hook blocks the session from ending and pushes the next
item. Draining the queue is what makes the terminal continue without re-prompting.

**Rule:** only genuinely actionable items go under Active. Anything waiting on a person
or an external system goes under BLOCKED with a different marker — an unchecked item that
cannot be completed turns the Stop hook into an unsatisfiable loop, which is the failure
mode `goal-circuit-breaker` exists to catch.

## Active

- [ ] `scripts/ci_local.sh` — one command that runs every gate the CI workflow runs
      (ruff, pytest tests/, pytest swarm/, check_provisioning, check_agent_registry,
      secrets_check, tsc, eslint, next build) and exits non-zero on the first failure.
      GitHub Actions has allocated no runner since 2026-08-14, so local parity is
      currently the *only* quality signal this repo has. Must print a per-gate
      pass/fail table, not just an exit code.
- [ ] `dashboard/vercel.json` has no `ignoreCommand`, so every push to `main` triggers a
      production build — including `docs(wiki): refresh per-directory WIKI.md [skip ci]`
      commits that touch no dashboard file. `[skip ci]` suppresses GitHub Actions but not
      Vercel. Add an Ignored Build Step keyed on whether the diff touches `dashboard/`.
      Efficiency only, low priority.
      CORRECTION: the five `BLOCKED` production deployments are NOT an ongoing fault and
      are not caused by this. They all fall between 03:59 and 05:20 on 2026-08-14 and the
      latest deployment (06:23:49Z, main's tip) is `READY`. No push to `main` has happened
      since, so that list is just the tail of that day. Do not build a fix on the BLOCKED
      premise.
- [ ] Verify `/health` surfaces what CLAUDE.md requires it to: a boolean that the autonomy
      loop will fire next tick, the timestamp of the last successful tick, and
      `linear_api_key: bool`. Confirm against `routes/health.py` + `health_full.py`; the
      unauthenticated shape is `{"status":"ok"}` only, so check the authed payload path.
- [ ] `.venv-verify/` is an 8,099-file virtualenv in the working tree that no script,
      workflow or doc references. Establish whether anything still needs it; if not,
      remove it and add it to `.gitignore` so it stops inflating local tooling runs.
- [ ] `secrets_check.py` rewrites `.gitignore` as a side effect of the default (non
      `--dry-run`) run. A check that mutates the tree it is checking is surprising —
      decide whether the write should move behind an explicit `--fix` flag, and record
      the decision either way.

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
