# WORK ORDER — PART 2: move the seven config files

**Pick this up in a fresh session. Everything needed is here; nothing needs re-deriving.**

Filed in `docs/` because `.harness/` is untracked and would not propagate.

---

## State on arrival

| | |
|---|---|
| Branch | `fix/config-loader-fail-loud`, tip **`b2b8ef7f`**, pushed, **not merged** |
| `origin/main` | `2a0ec492` — untouched, still deploy-broken at `Dockerfile:38` |
| Commits so far | `22a9d0e0` (1a loader) · `f0b31df0` `e5e61b99` `ba5c4eaa` `b2b8ef7f` (1b routing) |
| Full-suite baseline | **60** failed/error entries on `origin/main`, incl. 18 pre-existing collection errors (`tests._sprinkle_helpers` missing). 1b is also 60 — **zero new**. That 60 is the bar. |

PART 1 is complete and verified four ways (structural, behavioural, full suite, JS end-to-end).
Do not redo it.

---

## Scope — one commit

Move all seven to `config/harness/`, **tracked**:

`config.yaml` · `projects.json` · `cron-triggers.json` · `content_manifest.json` ·
`provisioned-tools.yaml` · `margot_identity.json` · `registry.yaml`

`margot_identity.json` keeps its subpath: `config/harness/margot/assets/margot_identity.json`.
`registry.yaml` keeps its subpath: `config/harness/agents/registry.yaml`.

### The lines that change

- **`app/server/config_loader.py`** — `CONFIG_DIR = REPO_ROOT / ".harness"` → `REPO_ROOT / "config" / "harness"`. **This is the only Python line.** Every consumer routes through it (PART 1).
- **`mcp/pi-ceo-server.js:50`** — `const CONFIG_DIR = HARNESS_DIR;` → the new location. **The only JS line.**
- **`Dockerfile:38`** — `COPY .harness/ ./.harness/` → copy `config/harness/`. **Must be in this same commit** — splitting it leaves a window where main cannot deploy, which is what this whole sequence exists to fix.
- **`scripts/morning_briefing.py:81`** — `executive-summary.md` **stays untracked**; make the reader tolerate absence.

### Rulings that still stand — do not re-litigate

- `.harness/` keeps its **blanket ignore**. No negative exceptions. No reclassification to
  `REVIEWED_FIXTURE`. The `not-committed` premise stays binary and machine-checkable.
  *(Verified empirically: staging even one `.harness` file makes `secrets_check.py` exit 2 with
  `the exclusion's premise is false`.)*
- `HARNESS_DIR` for `pi-ceo-server.js` is a **deployment** concern. Set it in the Dockerfile and
  in Railway config in this same commit. If Railway config is unreachable from the repo, record
  exactly what a human must change and where.

---

## The five verifications

1. **Secrets scanner** — runs, all exclusion preconditions hold, **exit 0** (not 2).
2. **Canary** — plant a credential-shaped string at `config/harness/`, confirm the scanner flags
   it **CRITICAL**, remove it. Without this, "no findings" from the new location is
   indistinguishable from a location nobody scans. *(Already proven to work: a canary at
   `config/harness/probe.yaml` was DETECTED CRITICAL while `.harness/` preconditions held.)*
3. **Docker build from a fresh clone of the branch SUCCEEDS.** This is the one that matters.
   Report before/after: previously `ERROR: "/.harness": not found` at line 38, now built.
   Include the build output line proving it.
4. **Model policy goldens from a clean clone** resolve planner opus, orchestrator opus, monitor
   haiku. **Add `adversary` to the goldens as opus** — it is the role nothing currently asserts,
   and it silently dropped to sonnet in the original regression.
5. **Full suite** before/after. **Zero new failures** against the 60 baseline.

Then commit, push, **do not merge**.

---

## Standing rules from the work order

- Report at the end of the part, not per step.
- Do not stop for a finding that fits a ruling; apply it and note it.
- **Stop** for: real money, production, merging, or a finding that **contradicts** a ruling.
- Same check failing three times = the approach is wrong. Stop and report.
- **Commit after every batch, before running any helper.**
- **No helper may contain `git checkout`/`reset`/`clean` or any discard op.** Cleanup removes
  only files it created, by name. *(A helper containing `git checkout -- .` destroyed a full
  batch of uncommitted work in PART 1.)*
- **Read any script before running it**, including one written earlier in the same session.

---

## Working tooling (scratchpad, re-createable from this doc if lost)

- `sweep.py` — filename-based structural check; enumerates tracked **and** untracked; exits
  non-zero while any direct construction remains.
- `plant_control.py` — plants two synthetic control files (Path-joined + multi-line), removes
  **only those two by name**. Required: without them the sweep's control reads 0/2 and a zero
  result means nothing.
- `behavioural.py` — points `CONFIG_DIR` at an empty dir and probes every consumer.
  **`AttributeError` is reported as PROBE-BROKEN, never as a pass.**

**The structural sweep alone is not sufficient.** In PART 1 it hit its exact target and was
clean while six consumers still returned empty. Run the behavioural arm and hunt for empty
returns explicitly.

---

## Out of scope — recorded, do not do

- `scripts/coverage_check.py:91` — takes `repo` as a parameter, dispatched from a probe table.
  Needs a caller determination someone makes deliberately.
- `_load_projects(repo_root)` in `swarm/portfolio_pulse_github.py` and `_linear.py` now **ignores
  its `repo_root` argument** — dead parameter, harmless today because production passes this
  repo. Remove deliberately, not as a side effect.
- `tests._sprinkle_helpers` is missing on `main`, causing 18 collection errors. Pre-existing.

---

## PART 3 (determinations only, after PART 2 passes)

Read-only. Determine why `main`'s **Smoke Test** and **Linear Evidence Audit** are red. For each:
cite the failing assertion and the deciding file and line; say whether it is the same class as
the model-policy regression, an unrelated defect, or a stale test; and state whether the fix
belongs in the current branch, its own branch, or is blocked. **Do not fix either.**

Known for context: main's **Prove-It Evals** red was already determined — three golden
assertions in `evals/test_model_policy_golden.py` failing because `.harness/config.yaml` is
absent from a clone, so `model_policy` fell open to sonnet. PART 1 fixed the fail-open; PART 2
restores the file to a tracked location. Smoke Test is **not** covered by that and is unexamined.
