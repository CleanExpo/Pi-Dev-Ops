# QUEUE

Read by the `keep-going.sh` Stop hook (`~/.claude/hooks/keep-going.sh`). While any
`- [ ]` item remains here, the hook blocks the session from ending and pushes the next
item. Draining the queue is what makes the terminal continue without re-prompting.

**Rule:** only genuinely actionable items go under Active. Anything waiting on a person
or an external system goes under BLOCKED with a different marker — an unchecked item that
cannot be completed turns the Stop hook into an unsatisfiable loop, which is the failure
mode `goal-circuit-breaker` exists to catch.

## Active

Audit of the nine "AI employee" pillars against what Pi-CEO already runs. Most were
already built — only the genuine gaps are listed. Pillars 3 (brief: `brief.py` PITER +
ADW), 4 (ticket: Linear routing), 6 (review: evaluator + judge), 7 (schedule:
`cron_scheduler` + routines), 8 (parallel: `/api/build/parallel`) and 9 (permissions:
autonomy ladder + `model_policy`) are present and were left alone.

- [ ] Pillar 5, "eyes" — **CONFIRMED ABSENT. Designed, deliberately not built tonight.**
      `_PHASE_ORDER` is `clone → analyze → claude_check → sandbox → plan → generator →
      evaluator → push`. No phase runs the product. `_phase_sandbox` only verifies the
      workspace directory exists (or re-clones it). `_phase_evaluate` is a pure diff
      reader: its prompt grades COMPLETENESS / CORRECTNESS / CONCISENESS / FORMAT /
      KARPATHY from the diff against the brief, and asks "any bugs, logic errors ... or
      broken tests?" without ever having run one. The system grades code by reading it.
      That is exactly the RA-1109 hazard this repo hardwired against ("HTTP 200, types
      compiling, and green lint are not shipping"), sitting in its own generator.
      DESIGN: a `verify` phase between `generator` and `evaluator` that runs the TARGET
      repo's own checks in the workspace (detect `npm test` / `pytest` / build) and feeds
      the captured result into the evaluator prompt, so the grade is grounded in execution
      rather than inference. NOT SHIPPED because the blast radius is wrong for tonight: it
      changes `_PHASE_ORDER`, the `total_phases` 5/6 arithmetic, and
      `dashboard/lib/phases.ts`, which parses the phase sequence — a cross-cutting change
      to the loop that ships code to 12 portfolio repos, while Actions allocates no runner
      to validate it. Same call as the Vercel `ignoreCommand`, for the same reason.
      (pillar 6 resolved as a decision — see Done)

## BLOCKED — founder action, do not treat as queue items

* **GitHub Actions allocates no runner** (since 2026-08-14T05:20Z). Needs a billing or
  infrastructure decision. Evidence and the three options:
  `docs/BLOCKER-github-actions-runners-2026-08-18.md`.
* **`/command-centre/wiki-graph` returns 500** — RA-7264. `route-exercise` is now the only
  failing gate, so `handoff-loop.sh` reports BLOCKED on every run. Pre-existing: the same
  500 appears in handoff logs from before today's cron work. Left as a ticket rather than
  fixed here, because a red gate that everyone learns to ignore is how a real regression
  gets waved through — it should be fixed deliberately, not folded into unrelated work.
* ~~**Mission Control authenticated payload unverified.**~~ **DISPROVEN 2026-08-18.** The
  premise was that `scripts/smoke_test.py` cannot authenticate without `.env.local`. It
  can: start the server with `TAO_PASSWORD` set and pass the same value to `--password`.
  Done, and the authenticated payload is now confirmed — 35/35 checks including
  `POST /api/login` 200, `tao_session` cookie set, `GET /api/me` → `authenticated:true`,
  and authenticated bodies for `/api/sessions`, `/api/lessons`, `/api/gc` and
  `/api/autonomy/status`. `.env.local` was never required for this.

## Done — 2026-08-18 overnight

- [x] Pillars 1 + 2 (workspace + memory) BUILT. A generated session got a three-line
      containment stub and none of the business context Pi-CEO already held. The planted
      `CLAUDE.md` now carries registry facts and the business charter, with the guard
      still first. `check_business_charters.py` added as a ratchet, both failure arms
      verified to fire.
- [x] Pillar 6 at the workspace level — DECISION: do not add a per-repo `REVIEW.md`. The
      evaluator's rubric (completeness / correctness / conciseness / format / Karpathy,
      with the threshold and confidence contract) lives in the server-side prompt and is
      applied uniformly to all 12 portfolio repos. A per-repo standard file would
      duplicate it and drift from it, and nothing in the generator reads one. The
      show-notes three-file setup is for a human working a single repo; the equivalent
      here is already central and enforced. Adding a third file to match a video would be
      the "unnecessary complexity" the rubric itself scores down.
- [x] Pillars 3, 4, 7, 8, 9 audited as ALREADY PRESENT and deliberately left alone:
      `brief.py` (PITER intent + ADW routing), Linear routing via `projects.json`,
      `cron_scheduler` + routines, `/api/build/parallel`, and the autonomy ladder +
      `model_policy` permission tiers.

- [x] CI's `smoke-local` reproduced locally: **35/35 checks pass**. But running it exposed a
      worse problem than the skip it was meant to close — the gate was **not hermetic**.
      `TAO_AUTONOMY_ENABLED=0` gates the Linear poller only; `cron_loop` is separate and
      ungated, and ten seconds after boot it fires every trigger whose `last_fired_at` is
      older than its schedule. Booting the server for a *test* therefore ran a real board
      meeting (live model calls, an Ollama call, a Claude Agent SDK subprocess) and wrote
      `.harness/board-meetings/2026-08-17-research.json`. CI is worse, not better: a fresh
      checkout takes `last_fired_at` straight from git, so every trigger is overdue there.
      Fixed with `TAO_CRON_ENABLED`, **default 1 so production is unchanged**, set to 0 in
      `ci.yml`'s smoke-local job and in `handoff-loop.sh`'s `_smoke_with_server`.
      Evidence: gate now reports `skip=0` (was `skip=1`) and **0** board-meeting artefacts
      where the pre-fix run produced 1. 9 new tests; suite 3234 passed. Positive control:
      removing the `if config.CRON_ENABLED` guard turns the suppression test red.
      Honest note: the very first smoke run of the session failed on `secrets_check`, and I
      could not reproduce it — I truncated its diagnostic output myself. The concurrent
      cron activity is the likely cause and is now gone, but that is inference, not proof.
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
- [x] CI's `smoke-local` reproduced locally — **35/35 checks passed**. That was the last CI
      job not yet verified here, so every CI job is now green locally.
- [x] `audit-smoke` was a control that could never fire: it ran only when a server
      HAPPENED to be on :7777, and nothing starts one — so it SKIPped every run while
      reporting a tidy SKIP that read like a considered decision. It now starts its own
      server (as ci.yml's `smoke-local` does), reuses a developer's if one is already
      listening, and only kills the process it started.
- [x] `build-dashboard` failed on every run because `next.config.ts` hard-fails without
      `PI_CEO_URL`/`PI_CEO_PASSWORD`, which ci.yml supplies and this runner did not —
      taking `route-exercise` down with it for want of a build to serve.
- [x] `audit-secrets` was poisoning itself: the gate tees findings, snippet included, into
      `.handoff-logs/`, and the next run rescanned that log and reported it as a fresh
      secret — so one real finding became permanent and outlived its own fix.
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
