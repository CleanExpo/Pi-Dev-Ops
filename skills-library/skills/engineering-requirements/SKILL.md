---
name: engineering-requirements
description: Use before any spec or non-trivial change becomes code — dispatches the principal-engineer bench (17 specialist seats) to return the engineering requirements the author did not know to ask for, merges them into a machine-checked engineering.md, and gates the build on it. Fires on "/bench", "/boris", "engineering requirements", "engineer this", "what am I missing", "review this properly", and automatically from /spm before a spec is final.
argument-hint: "<path to spec.md or a change description; defaults to ./spec.md or the branch diff>"
allowed-tools: Read, Grep, Glob, Bash, Write, Agent
updated: 2026-07-29
---

# engineering-requirements — the bench gates the build

The planning pipeline converts *what the author said* into a better-organised version of *what the
author said*. This skill performs the move nothing else performs: generating the requirements
nobody thought to ask for — then refusing to let the change become code until they are answered.

**A bench, not a reviewer.** Seventeen seats, each a principal engineer in one speciality, run in
parallel as independent lenses. The roster, ownership map and dispatch predicates live in
[`references/bench.md`](references/bench.md); the shared output contract lives in
`~/.claude/agents/bench/CONTRACT.md`.

Why a bench and not a longer prompt: on 2026-07-29 a generalist review of an RLS incident concluded
the exposure was limited to application-encrypted OAuth tokens. A drift lens on the same repository
in the same hour found nine surviving `"Anon read access"` policies, sourced from an untracked
bootstrap file the generalist never opened, exposing 11,007 rows of plaintext client financial
data. Breadth is not depth repeated.

## Procedure

### 1. Locate the change

`$ARGUMENTS` if given; else `./spec.md`; else the branch diff against `merge-base`. If there is
neither a spec nor a diff, say so and stop — this reviews something, it does not invent it.

### 2. Select the seats

Apply the predicates in [`references/bench.md`](references/bench.md) against the changed paths, the
spec text, and the repo. The core four (`boris`, `eng-failure`, `eng-observability`, `eng-test`)
always sit. Everything else is earned.

Announce the seated bench and why, in one line each. Selection is auditable or it is vibes.

**`eng-release` seats unconditionally when the migration ledger disagrees with the migration
directory.** That is a standing condition, not a kind of change, and it is the exact failure that
let a correct security migration sit unapplied for five and a half months. Determine it by running
the check, not by judgement:

```bash
python3 ~/.claude/skills/engineering-requirements/scripts/migration_drift.py check \
  --root <repo> --db-url "$DRIFT_DB_URL"
```

Exit 0 in sync, 1 drift — seat `eng-release`, 2 cannot determine — **also seat `eng-release`**, and
say so. A check that cannot see the database is the same silent fail-open it exists to catch, so
"we could not tell" seats the reviewer rather than excusing him.

If more than ten seats are earned, stop and return a decomposition instead of a review: a change
that spans the whole bench is too big, and that is itself the finding.

### 3. Run them cold, in parallel

Spawn each seat with the **Agent tool**, `subagent_type: "<seat name>"`, in a single message so
they run concurrently. Give each: the change, the repo root, `round: 1`, and nothing else — no
summary of the change, no account of why it was written that way, no other seat's findings. A seat
that has read another seat's output is no longer an independent lens, and a warm reviewer inherits
the author's rationalisations.

If a seat's `subagent_type` is not found, the agent registry loaded before the bench existed —
spawn `general-purpose` on Opus and open with *"read `~/.claude/agents/bench/<seat>.md` and
`~/.claude/agents/bench/CONTRACT.md`, and adopt them completely for this task."* The registry picks
the bench up at the next session start.

**Do not review it yourself.** A model grading its own planning output is the failure this exists
to prevent.

### 4. Merge into one artifact

Write `engineering.md` beside the spec. Every category carries `by:` naming the seat that answered
it, so coverage is auditable and a finding can be traced to a lens.

```yaml
---
type: engineering-requirements
spec: ./spec.md
spec_sha256: <shasum -a 256 of the spec exactly as reviewed>
reviewer: bench
seated: [boris, eng-data, eng-authz, eng-failure, eng-observability, eng-test]
reviewed_at: <ISO-8601 with offset>
status: BLOCKED
categories:
  data_model:         {state: PRESCRIBED, ref: "#data-model", by: eng-data, blocking: true}
  invariants:         {state: DECIDED,    ref: "#invariants", by: eng-authz}
  failure_modes:      {state: DECIDED,    ref: "#failure-modes", by: eng-failure}
  interface_contract: {state: N/A,        reason: "<structural fact about THIS change>", by: boris}
  concurrency:        {state: N/A,        reason: "<structural fact about THIS change>", by: boris}
  migration:          {state: DECIDED,    ref: "#migration", by: eng-data}
  rollback:           {state: DEFERRED,   reason: "<the condition that forces it back>", by: boris}
  observability:      {state: DECIDED,    ref: "#observability", by: eng-observability}
  budget:             {state: DEFERRED,   reason: "<the event that makes a budget real>", by: boris}
  test_oracle:        {state: PRESCRIBED, ref: "#test-oracle", by: eng-test}
disagreements:
  - "eng-data says X; eng-concurrency says Y; chair ruled X because Z"
---
```

All ten categories, every time — a category no seated specialist owns falls to the chair, so the
contract never weakens because the bench was small. Then one `##` section per
`DECIDED`/`PRESCRIBED` category matching its `ref` anchor.

`status` is derived from `blocking`, never chosen. Record disagreements rather than averaging them.

### 5. Run the gate

```bash
python3 ~/.claude/skills/engineering-requirements/scripts/engineering_gate.py --spec <spec.md>
```

Exit 0 = PASS. Exit 1 = BLOCKED, reasons on stderr. **Fix the artifact, never the validator** — if
the gate is wrong that is a bug, and the fix starts with a failing test.

### 6. Report

State what the bench found that the change did not contain, and which seat found it. That sentence
is the whole value of the layer; if there is nothing to say, say that too — it is a real signal
that either the change was already good or the bench is mis-calibrated.

## The ten categories

`data_model` · `invariants` · `failure_modes` · `interface_contract` · `concurrency` ·
`migration` · `rollback` · `observability` · `budget` · `test_oracle`

Legal states: `DECIDED` + ref (the change answers it, and the section quotes it), `PRESCRIBED` +
ref (a seat supplies the answer), `DEFERRED` + reason, `N/A` + reason. Definitions and worked
examples in [`references/categories.md`](references/categories.md).

**`PRESCRIBED` is not a softer `DECIDED`.** It marks a requirement a reviewer invented, so you can
overturn it without re-triggering review. A fabricated latency budget filed as `DECIDED` ends up on
a dashboard as fact.

**Most changes are small, and a short review passes.** On something that writes nothing to disk,
`data_model`/`migration`/`concurrency` being `N/A` is the correct output. The gate exists to stop
silent skipping, not to extract ten paragraphs from a CLI flag.

## Where this binds

| Point | Behaviour |
|---|---|
| `/spm` step 7a | A spec is not final until the gate exits 0. |
| `pr_release_gate.py` | If the branch diff adds or edits a `spec.md`, its sibling `engineering.md` must exist and validate before push or PR. |
| Everything else | Inert — no spec in the diff, no gate. |

Scoping to the branch diff is what makes "new work only" true: a spec that predates the bench and
is untouched does not block, and editing one pulls it back into scope, which is correct because the
review binds to content rather than to a date.

## Scope

- Seats are read-only and never edit code.
- This does not replace `judge` (*should we build this?*) or `spm` (*what should we build?*). It
  answers *what will break when we do*.
- Adding a seat requires naming a failure class the existing seventeen provably missed, with the
  incident that proves it.
