# Branch triage — 2026-09-10

**What this is:** every branch on `github.com/CleanExpo/Pi-Dev-Ops`, with a
one-line verdict, so "no missing branches" becomes a finite list instead of a
worry.

**Baseline:** `origin/main` at `26b9484e`, read from a fresh clone on 2026-09-10.

**Status of these verdicts — read this first.** Each verdict below is a
**proposal**, not a result. The evidence behind it is the commit subjects and
the divergence count, both read directly from the repository. What has **not**
been checked is whether any branch rebases cleanly or passes the gate — that
needs the test suite running locally, which is currently blocked (see
"Blocked" at the end). No branch is deleted, rebased or merged on the strength
of this document alone.

**One correction to an earlier count.** A stale local checkout listed 30 remote
branches. The live remote has **25**. Five branches were deleted on GitHub since
that checkout last fetched, so any plan built on the old list was counting
branches that no longer exist.

---

## 1. Safe to delete — already fully merged (0 commits ahead of main)

Nothing is lost; every commit is already in `main`.

| Branch | Behind main | Last commit |
|---|---|---|
| `tao/codebase-wiki-refresh` | 85 | 2026-09-06 |
| `feature/control-goal-flow-harden` | 69 | 2026-09-06 |
| `fix/prod-slack-health-receipt` | 281 | 2026-08-28 |
| `feat/goal-to-linear-ticket` | 428 | 2026-08-19 |

## 2. Safe to delete — throwaway probes and a bot mis-commit

| Branch | Commits | What it holds |
|---|---|---|
| `probe/merge-actor-canary` | 1 | `test(canary): probe whether the merge actor is still live` — a one-off probe |
| `scratch/merge-actor-probe-20260805` | 1 | `chore(probe): whitespace-only, merge-actor observation probe` — whitespace only |
| `wt/kanban-fixture-isolation-20260721` | 1 | A commit whose message is a leaked AI prompt (see §5) — no recoverable intent |

## 3. Land first — small, self-contained, and one of them is a security fix

| Branch | Commits | What it does | Why now |
|---|---|---|---|
| **`hotfix/method-aware-auth-classification`** | 2 | `fix(security): method-aware auth classification + close two unauthenticated GETs` | **Security.** Two unauthenticated GET endpoints have been open since 2026-08-02. Highest priority on this page. One of its two commits is a junk commit (§5) and should be dropped in the rebase. |
| `fix/linear-pulse-surface-graphql-errors` | 1 | `fix(pulse): say WHY the Linear heartbeat was refused` | Touches the same pulse path as Mission Control defect C. Land it with that fix so the heartbeat both reads the right file and explains itself when it fails. |
| `fix/curator-proposals-contract` | 2 | Aligns the curator allow-list with the contract upstream actually sends | Small, and one commit removes a test asserting a payload upstream cannot produce — a dead check. |
| `fix/guard-oserror-and-zombie-reap` | 3 | Reaps a zombie child; surfaces a failed containment-guard write | Its own tests assert the grandchild **died**, not merely that it started — a real control. |
| `fix/openrouter-first-paid-tiers` | 3 | Routes paid tiers to OpenRouter first; falls back to Anthropic when OpenRouter is down, not only when unfunded | Matches the estate's cost law (free/subscription lanes before metered). |

## 4. Land after review — medium, worth having

| Branch | Commits | What it does |
|---|---|---|
| **`feat/mission-control-model-fabric`** | 12 | The `/control/model` routing panel. Already scheduled as Phase 2 of the Mission Control work. |
| `fix/ci-quota-diagnosis` | 10 | Documentation only. Corrects 21 stale `.harness/projects.json` paths and several overstated claims about what the gates enforce. Low risk, high accuracy value. |
| `fix/ruff-version-drift` | 6 | Makes the ruff-pin check fail closed and stop grading against the wrong rule set. A gate that was silently mis-measuring. |
| `feat/liveness-prover` | 5 | Proves the estate is alive rather than asking whether it errored. Includes a fix stopping the runner executing code from a world-writable path. |
| `feat/rolling-15-step-continuation-hook` | 9 | Cross-channel rolling execution horizon, including `feat: expose continuation bridge in Mission Control`. Overlaps the Mission Control surface — sequence it after the defect repairs so the two do not collide. |

## 5. Needs your call — large blast radius or unclear intent

| Branch | Commits | The problem |
|---|---|---|
| `fix/harness-entry-root` **and** `feat/senior-harness-advisory-board` | 51 each | **These are near-duplicates** — they share 13 of their commits and differ only at the tip. Landing both would apply the same work twice. One coherent branch should be chosen and the other deleted. Both are 389 commits behind main. |
| `fix/config-loader-fail-loud` | 16 | Moves seven config files to `config/harness/` and reroutes every reader. Wide blast radius across tests, evals and JS config paths. Valuable, but it touches everything and needs its own slot. |
| `repair/pr600-tenant-run-alert-contract-20260722-v2` | 9 | CCW six-pager health consumers, fail-closed. Real work, but 2 of the 9 commits are junk (§5) and it is 503 commits behind. |
| `pr590-merge` | 6 | Weekly cross-repo enhancement loop + a goal circuit-breaker. 2 of 6 commits are junk. The branch name suggests it was a merge staging area, not a feature. |

## 6. Leave alone

| Branch | Why |
|---|---|
| `archive/pi-ceo-local-main-jun21` | Named as an archive. 579 commits ahead, 1420 behind — it is a snapshot of a different history, not a branch to land. |

---

## A defect this triage uncovered

**Five commits across three branches have an AI prompt as their commit message**,
beginning `You are the chief-of-staff synthesising a daily portfolio pulse for
P…` — one on `wt/kanban-fixture-isolation-20260721`, two on `pr590-merge`, two on
`repair/pr600-tenant-run-alert-contract-20260722-v2`.

A sixth commit, on `hotfix/method-aware-auth-classification`, has a leaked
Windows temp path as its message (`Read C:\Users\DISAST~1\AppData\Local\Temp\…`).

Something in the automated commit path is writing the model's *prompt*, or a
stray tool argument, into the commit message instead of a summary. That is worth finding, because the commit
log is the only record of why a change was made, and these commits have no
recoverable intent. Filed as a separate item — it is a producer defect, not a
branch problem, and deleting the branches would hide it rather than fix it.

---

## Blocked

The verdicts above cannot be upgraded from *proposed* to *proven* until the test
suite runs locally, and installing the project's Python dependencies is
currently refused by this session's permission classifier. The single command
that needs approval is recorded in the session report. Until it runs, no branch
here is touched.
