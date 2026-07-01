# Nexus Concierge OS — Validation & Commit Gate

**Owner:** Pi-Dev-Ops · **Issue:** RA-6815 · **Milestone:** Phase 0 — Nexus Concierge OS validation gate
**Status:** canonical. Every Nexus Concierge OS issue passes this gate before it is closed.

Pi-Dev-Ops owns the *safe build process* for Nexus Concierge OS: spec → issue → branch →
scoped change → validation → evidence → commit → push → PR → Linear. This document is the
single gate all OS issues (UNI-2170 core, UNI-2171 Lodgey, RA-6812 RestoreAssist, and the
secondary verticals) run through. It composes the existing Pi-Dev-Ops gate scripts — it does
not replace them.

Source of truth for the pickup order and work rules: the Linear document
*"Master CLI Agent Prompt — Nexus Concierge OS"*. This file is its committed, enforceable form.

---

## 1. Repo path conventions

| What | Where |
|---|---|
| Pi-Dev-Ops process/gate docs | `docs/nexus-concierge-os/` (this dir) |
| OS core engine + spec | per the owning issue (UNI-2170); do **not** place vertical code here |
| Vertical packs | each vertical stays in its own project/repo — **never mix verticals in one branch** |
| Validation scripts | `scripts/` (`handoff-loop.sh`, `autonomous_gate.sh`) |
| Evidence logs | `.handoff-logs/handoff-<ts>.log` (written by `handoff-loop.sh`) |

## 2. Branch naming (reconciled rule)

The Master prompt says "use the Linear branch name"; the Pi-Dev-Ops autogit guard only
protects branches prefixed `feat/` or `fix/`. Reconcile both:

```
feat/<linear-id>-<short-slug>     # new capability      e.g. feat/ra-6815-nexus-concierge-validation-gate
fix/<linear-id>-<short-slug>      # bug/regression fix  e.g. fix/uni-2171-lodgey-srt-mapping
```

- The `<linear-id>` (lowercased, e.g. `ra-6815`) ties the branch to its issue.
- The `feat/`/`fix/` prefix keeps the branch inside the autogit-guard's protected set.
- **Always** `git checkout -B feat/<...> origin/main` — branch from a freshly-fetched
  `origin/main`, never from a stale local `main`.

## 3. Build / validation playbook (the algorithm)

Run per issue, in order. Stop at the first hard failure and report (see §8).

1. **Read the issue fully** (`get_issue`) — scope, acceptance criteria, `gitBranchName`,
   linked docs. Read before editing.
2. **Branch** off fresh `origin/main` per §2.
3. **Make only the scoped change.** No adjacent refactors, no second vertical, no
   speculative work. Every changed line must trace to the issue.
4. **Validate locally** with the repo-canonical gate:
   ```bash
   scripts/handoff-loop.sh          # repo-adaptive definition-of-done; exit 0 = green
   ```
   `handoff-loop.sh` runs the canonical checks for whatever stacks the repo has and
   SKIPs (not fails) a gate whose stack is absent. See §4 for the underlying commands.
5. **Warnings disposition.** Every warning is either *fixed* or *explicitly accepted by
   Phill* (recorded in the evidence comment). A warning is never silently left.
6. **Commit** only after local validation is green (§6 format).
7. **Push** the branch and open a PR.
8. **Gate CI to green** — CI is the source of truth (local toolchain may be unprovisioned):
   ```bash
   scripts/autonomous_gate.sh CleanExpo/Pi-Dev-Ops <pr_number>   # exit 0 = all green
   ```
   On red: `gh run view <id> --log-failed`, fix on the same branch, repeat.
9. **Post evidence** back to the Linear issue (§5) — required before any close.
10. **Do not merge.** Merges are human-gated (some Pi-Dev-Ops PRs auto-merge by repo
    policy — that is the repo bot, not the agent). Do not self-merge.

## 4. Validation command list

**Pi-Dev-Ops canonical** (the CI jobs that must be green — the authoritative gate):

| Gate | Command | CI job |
|---|---|---|
| Python | `pytest -q` + `ruff check .` | `Python (pytest + ruff)` |
| Frontend | `tsc --noEmit` + `eslint` + build | `Frontend (tsc + eslint + build)` |
| Smoke | API smoke checks | `Pi CEO API smoke test` |
| Secrets | secret-exposure scan | `Secrets exposure scan` |

Prefer `scripts/handoff-loop.sh`, which invokes the applicable subset repo-adaptively.

**Generic fallback** (JS/TS repo with no repo-specific commands — per Master prompt):

```text
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## 5. Evidence comment template (post to the Linear issue before closing)

```md
## Validation evidence

Branch: <feat/fix-branch>
Commit: <short-hash>
PR: #<n>
Files changed:
- <file>

Commands run:
- <command> → <result>

Result: PASS | FAIL
Warnings: none | <listed, each fixed or "accepted by Phill">
Push result: pushed | not pushed
CI: green (<gate summary>) | red (<failing checks>)
Notes: <anything Phill needs to know>
```

## 6. Commit message & push-handoff format

**Commit message:**

```
<type>(<scope>): <imperative summary>   # type ∈ feat|fix|docs|chore|refactor|test

<why + what, wrapped ~72 col. Reference the Linear id (RA-####/UNI-####).>

Co-Authored-By: Claude <model> <noreply@anthropic.com>
```

**Push handoff (what the agent reports after push):**

```
Issue:   <RA-####> — <title>
Branch:  <feat/fix-branch> @ <short-hash>
PR:      #<n> — <url>
CI:      <green|red|pending> (<gate summary>)
Scope:   <one line — what changed, what did NOT>
Next:    awaiting human merge (do not self-merge)
```

## 7. Per-issue checklist (Definition of Done)

- [ ] Issue read fully; work scoped to it only (no vertical-mixing, no adjacent changes).
- [ ] Branch `feat/<id>-…` or `fix/<id>-…` off fresh `origin/main`.
- [ ] Change made; every changed line traces to the issue.
- [ ] `scripts/handoff-loop.sh` green locally (or SKIP with stated reason).
- [ ] Warnings each fixed or explicitly accepted by Phill.
- [ ] Committed (§6 format) only after green validation.
- [ ] Pushed; PR opened.
- [ ] CI gated to green via `scripts/autonomous_gate.sh` (CI = source of truth).
- [ ] Evidence comment (§5) posted to the Linear issue: branch, commit, files, validation summary.
- [ ] **Not** self-merged (human-gated).

## 8. No-close-until-green rule & stop conditions

**No-close rule:** an OS issue may be moved to Done only when (a) the evidence comment is
posted with branch + commit + files-changed + validation summary, and (b) CI is 100% green.
No branch, no commit, no evidence → no close.

**Stop and report (do not push through)** if:

- the issue is ambiguous or under-specified,
- the target repo path is missing,
- validation fails and cannot be made green within scope,
- credentials/secrets are missing (never paste secrets; keys live in `~/.hermes/.env`),
- production deployment is required (OS gate work is branch-only; no prod db-push, no deploy),
- the task crosses another project/vertical boundary.

---

## Cross-refs

- Linear doc *"Master CLI Agent Prompt — Nexus Concierge OS"* — pickup order + work rules (source).
- `scripts/handoff-loop.sh` — repo-adaptive definition-of-done gate.
- `scripts/autonomous_gate.sh` — PR-checks-to-green poller.
- `docs/ship-chain/00-index.md` — the underlying ship algorithm.
- `adrs/004-implementation-conventions.md` — repo implementation conventions.
