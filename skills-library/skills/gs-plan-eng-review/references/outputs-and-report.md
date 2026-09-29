# Final planning decisions, approval readiness, required outputs, report and navigation

## Final planning decisions

After Sections 1–4 and the Outside Voice path, resolve the TODO choices below. Then run the approval check before preparing final outputs.

### TODOS.md updates
Review every potential TODO. Reuse an exact prior disposition under Decision procedure; ask about each unanswered proposal in its own AskUserQuestion. Never batch TODOs or silently skip them. Per item: What, Why, Pros, Cons, Context, Effort (human / CC), Priority (P1/P2/P3), Depends on.

For each TODO, describe:
* **What:** One-line description of the work.
* **Why:** The concrete problem it solves or value it unlocks.
* **Pros:** What you gain by doing this work.
* **Cons:** Cost, complexity, or risks of doing it.
* **Context:** Enough detail that someone picking this up in 3 months understands the motivation, the current state, and where to start.
* **Depends on / blocked by:** Any prerequisites or ordering constraints.

Then present options: **A)** Add to TODOS.md **B)** Skip — not valuable enough **C)** Build it now in this PR instead of deferring.

Option C records accepted implementation scope; still do not edit product code.

Record this context with each accepted TODO; a vague bullet is insufficient.

## Approval readiness

Before Required outputs, check the ledger against every accepted remedy. Each
must cite its own actual answer, exact prior approval or authorized auto-decision;
setup, mode, approach and navigation do not count. Carry forward an exact approved
regression contract. Otherwise, its behavior and assertions need one dedicated
decision. If approval is missing, mark that draft pending, resolve the choice
through Decision procedure and repeat this check. Deferrals remain unresolved.
Only the ledger is needed here; completion outputs and logs come next.

At the end of `## Decision ledger`, record `Approval readiness: PASS` with the
checked IDs and actual answer references. A substantive change invalidates this
result; navigation alone does not. Continue to Required outputs, preserving
unresolved decisions in the report.

## Required outputs

Run this finish sequence after Approval readiness passes. The reference sections
below supply content, formats and commands for the named step; they do not start
another review cycle.

On recovery, resume at the failed step. Reuse a successful Review Log for
unchanged saved outputs; changed outputs must pass steps 1–4 again.

1. **Prepare the review body.** Use the output reference below to complete the
   working plan, Implementation Tasks and Completion summary. Derive unresolved
   choices from each record's current State, actual answer and accepted scope;
   leave them pending. Save permitted auxiliary artifacts under the write policy.
2. **Save and Read back.** Use Plan File Review Report to save the complete body
   and append its terminal `## GS REVIEW REPORT`. Pass that writer's Read-back
   gate. If report persistence is forbidden or the save cannot be recovered,
   follow **Blocked outcome**; do not continue to logging.
3. **Log the saved review.** Run Review Log with the saved Completion summary's
   values. If the required log is forbidden, show its fields as not persisted
   and take **Blocked outcome**. If it fails, apply the write policy's recovery.
   Neither case supplies completion or saved-dashboard credit.
4. **Publish.** Display the Review Readiness Dashboard, then present the saved
   Completion summary to the user.
5. **Choose navigation.** Use Next Steps — Review Chaining and wait for its answer.
   Navigation grants no implementation authority. If a substantive change arises,
   resolve it through Decision procedure, repeat Approval readiness, and redo the
   affected outputs from step 1 through publication before asking navigation again.
6. **Finish.** Return to the entrypoint's Section self-check and read-only
   EXIT PLAN MODE GATE. Run these checks in every host mode. Only after both
   pass, call ExitPlanMode, and only in host plan mode.

### Output reference — review body

Keep the working plan, findings, ledger and the sections below together in the
report file. Place `Suppressed findings` as a body appendix before the terminal
`## GS REVIEW REPORT`; nothing follows that terminal report.

### "NOT in scope" section
List considered work that was explicitly deferred, with one sentence explaining each deferral.

### "What already exists" section
List existing code or flows that partly solve the problem. Say whether the working plan reuses them or unnecessarily rebuilds them.

### Diagrams
Use ASCII diagrams for non-trivial data flows, state machines and pipelines. Name implementation files that need inline diagrams, especially complex model transitions, service pipelines and non-obvious mixin behavior.

### Failure modes
For each new path in the test diagram, name a realistic production failure and whether:
1. A test covers that failure
2. Error handling exists for it
3. The user would see a clear error or a silent failure

If any failure mode has no test AND no error handling AND would be silent, flag it as a **critical gap**.

### Worktree parallelization strategy

Group implementation steps for parallel git worktrees (`isolation: "worktree"`
or parallel workspaces).

With one primary module or fewer than 2 independent workstreams, write:
"Sequential implementation, no parallelization opportunity."

**Otherwise, produce:**

1. **Dependency table** — for each implementation step/workstream:

| Step | Modules touched | Depends on |
|------|----------------|------------|
| (step name) | (directories/modules, NOT specific files) | (other steps, or —) |

Use modules/directories, not guessed files: plans describe intent.

2. **Parallel lanes:** separate independent, disjoint modules; sequence shared
   modules together and dependencies later.

Format: `Lane A: step1 → step2 (sequential, shared models/)` / `Lane B: step3 (independent)`

3. **Execution order:** name launch/wait points: "Launch A + B in parallel worktrees. Merge both. Then C."

4. **Conflict flags:** name shared modules across parallel lanes and recommend
   sequential execution or coordination to avoid merge conflicts.

## Implementation Tasks

Before closing this review, synthesize the findings above into a flat list of
build-actionable tasks. Each task derives from a specific finding — no padding.
Always emit the markdown section. Write its JSONL artifact for `/gs-autoplan` only when the Review record and write policy permits it; otherwise label the complete task output not persisted and do not claim an aggregation artifact exists.

### Markdown section (always emit)

```markdown
## Implementation Tasks
Synthesized from this review's findings. Each task derives from a specific
finding above. Run with Claude Code or Codex; checkbox as you ship.

- [ ] **T1 (P1, human: ~2h / CC: ~15min)** — <component> — <imperative title>
  - Surfaced by: <section name> — <specific finding text or line reference>
  - Files: <paths to touch>
  - Verify: <test command or manual check>
- [ ] **T2 (P2, human: ~30min / CC: ~5min)** — ...
```

Rules:
- P1 blocks ship; P2 should land same branch; P3 is a follow-up TODO.
- If a finding produced no actionable task, do not invent one.
- If a section had zero findings, emit `_No new tasks from <section>._`
- Show human-team and CC effort estimates. Default task-type ratios (human ÷ CC time): scaffolding ~100x, tests ~50x, features ~30x, bug fix with regression ~20x, architecture ~5x, research ~3x. Adjust to the actual work and state the assumption.

### JSONL artifact (write when permitted, including zero tasks)

`/gs-autoplan` reads this file to aggregate across phases. Build each line with
`jq -nc` so titles and source findings containing quotes, newlines, or
backslashes serialize cleanly — never use hand-rolled `echo` / `printf`.

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
TASKS_DIR="${HOME}/.local/state/gs/projects/${SLUG:-unknown}"
mkdir -p "$TASKS_DIR"
TASKS_FILE="$TASKS_DIR/tasks-eng-review-$(date +%Y%m%d-%H%M%S).jsonl"
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)
BRANCH=$(git branch --show-current 2>/dev/null || echo unknown)
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"

# Repeat ONE jq invocation per task identified during this review.
# Substitute the placeholders inline with shell variables you set per task:
#   TASK_ID (T1, T2, ...), PRIORITY (P1/P2/P3), COMPONENT, TITLE,
#   SOURCE_FINDING, EFFORT_HUMAN, EFFORT_CC, FILES_JSON (a JSON array literal
#   like '["browse/src/sanitize.ts","browse/src/server.ts"]').
jq -nc \
  --arg phase 'eng-review' \
  --arg run_id "$RUN_ID" \
  --arg branch "$BRANCH" \
  --arg commit "$COMMIT" \
  --arg id "$TASK_ID" \
  --arg priority "$PRIORITY" \
  --arg component "$COMPONENT" \
  --arg effort_human "$EFFORT_HUMAN" \
  --arg effort_cc "$EFFORT_CC" \
  --arg title "$TITLE" \
  --arg source_finding "$SOURCE_FINDING" \
  --argjson files "$FILES_JSON" \
  '{phase:$phase, run_id:$run_id, branch:$branch, commit:$commit, id:$id, priority:$priority, component:$component, files:$files, effort_human:$effort_human, effort_cc:$effort_cc, title:$title, source_finding:$source_finding}' \
  >> "$TASKS_FILE"
```

If `jq` is not installed, fall back to skipping the JSONL write and warn
the user to install jq for autoplan aggregation. Never hand-roll JSONL.

When writes are permitted and zero tasks were identified, touch the JSONL file
(`: > "$TASKS_FILE"`) so the aggregator sees that the phase produced output
this run (an empty file means "ran, no findings" — distinct from "didn't run").


### Unresolved decisions
List unanswered or interrupted choices as "Unresolved decisions that may bite you later", with their IDs and missing answers. Never default silently. Count each open choice once, separately from prior reviews; the terminal report adds those independently.

### Completion summary
Use the final decision record and outputs. The finish sequence publishes this summary after the report Read-back and Review Log:
- Step 0: Scope Challenge — ___ (scope accepted as-is / scope reduced per recommendation)
- Architecture Review: ___ issues found
- Code Quality Review: ___ issues found
- Test Review: diagram produced, ___ gaps identified
- Performance Review: ___ issues found
- NOT in scope: written
- What already exists: written
- TODOS.md updates: ___ items proposed to user
- Failure modes: ___ critical gaps flagged
- Unresolved decisions: ___ in this review
- Outside voice: recorded provider, completed / unavailable / disabled / skipped (reason)
- Parallelization: ___ lanes, ___ parallel / ___ sequential
- Lake Score: X/Y. Y counts answered coverage choices; X counts those selecting 10/10. Exclude choices that differ in kind; use N/A when Y is zero.

## Plan File Review Report

In finish step 2, save the working plan and complete review body with the terminal report below. Apply **Review record and write policy**.

### Use the selected report file

Use the report file already selected under **Review record and write policy**. Do not choose another destination here.

### Generate the report

Read the review history (references/review-log.md, "Read the history") for prior review entries.
Use the current Completion Summary for this review's status and findings;
apply the Review Log field rules below and add exactly one to its prior run count.
Do not pre-log this run to populate the report.
Use prior entries for other reviews, retaining their status, attribution and freshness.

Parse each JSONL entry using recorded provenance. Historical source "claude" is a native Claude subagent; "claude-code" is the external CLI. Keep historical codex identifiers and never relabel old records from the current harness. Unknown model identity remains unknown. For new records, show host, outside_provider, outside_status, and phase. Only completed external records establish outside coverage; native fallbacks do not.

Each skill logs different fields:

- **plan-ceo-review**: `status`, `unresolved`, `critical_gaps`, `mode`, `scope_proposed`, `scope_accepted`, `scope_deferred`, `commit`
  → Findings: "{scope_proposed} proposals, {scope_accepted} accepted, {scope_deferred} deferred"
  → If scope fields are 0 or missing (HOLD/REDUCTION mode): "mode: {mode}, {critical_gaps} critical gaps"
- **plan-eng-review**: `status`, `unresolved`, `critical_gaps`, `issues_found`, `mode`, `commit`
  → Findings: "{issues_found} issues, {critical_gaps} critical gaps"

The current row describes this actual review. Mark an unlogged current run as not persisted; do not present it as a saved dashboard entry.

Display `clean` as CLEAR and `issues_open` as ISSUES OPEN, retaining freshness and not-persisted labels. Other statuses keep their recorded meaning.

Produce this markdown table:

```markdown
## GS REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/gs-plan-ceo-review` | Scope & strategy | {runs} | {status} | {findings} |
| Outside Review | {recorded provider and trigger} | Independent 2nd opinion | {runs} | {outside_status} | {findings} |
| Eng Review | `/gs-plan-eng-review` | Architecture & tests (required) | {runs} | {status} | {findings} |
```

Below the table, add these lines. **OUTSIDE COVERAGE** and **CROSS-MODEL** are conditional:
include them when the phase ran, was disabled/skipped/unavailable, or has findings;
omit them only when no such phase applies. **VERDICT** is always present:

- **OUTSIDE COVERAGE:** provider, phase, completion state, and findings. Include unavailable, disabled, and skipped phases; never infer completion from another phase.
- **CROSS-MODEL:** only when native and completed external reviews exist — overlap analysis with recorded providers and known model identity. Do not infer distinct model families from harness names.
- **VERDICT:** list reviews that are CLEAR (e.g., "CEO + ENG CLEARED — ready to implement").
  If Eng Review is not CLEAR and not skipped globally, append "eng review required".

**Unresolved-decisions status (MANDATORY — never omitted; the report's final non-whitespace
line).** After VERDICT, end the report (content under the `## GS REVIEW REPORT`
heading — a bold label, never a new `## ` heading; exempt from the "omit when empty"
rule) with exactly one: the exact unbolded line `NO UNRESOLVED DECISIONS` (a bolded one
does NOT count), OR a `**UNRESOLVED DECISIONS:**` header + one bullet per open item
(last bullet = final line; add `+ N unresolved from prior reviews` only when N > 0).
This avoids double-counting: list THIS review's open items from context; for prior reviews
sum `unresolved` over the latest fresh row per skill (dashboard 7-day window) after you
DROP the current skill's row; emit the sentinel only when both are zero.

### Write to the report file

If the report destination is absent or writing is forbidden, assemble the same complete working plan, review output and terminal report in chat, labeled not persisted. Do not run the file-writing steps below or claim their Read-back gate passed. Then follow **Blocked outcome** in the entrypoint. Otherwise save only accepted changes, keeping unresolved choices pending:

The report must always be the LAST section of the report file — never mid-file.
Use a single delete-then-append flow:

1. Read the existing report file, if present. Preserve its content and apply only
   accepted changes; include the full review output. Locate any existing
   `## GS REVIEW REPORT` section.
2. If found, use the Edit tool to DELETE the entire existing section. Match from
   `## GS REVIEW REPORT` through either the next `## ` heading or end of
   file, whichever comes first. Replace with the empty string. This applies
   regardless of where the section currently lives — mid-file deletion is
   intentional, not a special case. If the Edit fails (e.g., concurrent edit
   changed the content), re-read the report file and retry once.
3. If a report was deleted, Read the updated file. Append the new
   `## GS REVIEW REPORT` at EOF. Use Edit to match the suffix
   confirmed by the latest Read, or Write the full file with the report last. Append whether or not a prior report existed.
   "Unresolved Decisions" is not an EOF anchor when other sections follow it.
4. **Read-back gate:** Read the saved file. Verify the accepted changes, full review
   output, current review row, verdict and final unresolved-decisions status, with
   `## GS REVIEW REPORT` as the last section. If writing or verification fails,
   report the error and follow **Blocked outcome** before Review Log or decision logging.

Do NOT replace the section in place; delete it and append the new report at EOF.

## Review Log

Use this command in finish step 3, after successful Read-back. The required review log follows the write policy.

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
echo '{"skill":"plan-eng-review","timestamp":"TIMESTAMP","status":"STATUS","unresolved":N,"critical_gaps":N,"issues_found":N,"mode":"MODE","commit":"COMMIT"}' >> "$GS_PROJ/$BRANCH-reviews.jsonl" && echo LOGGED || echo "NOT PERSISTED"
```

Substitute values from the Completion Summary:
- **TIMESTAMP**: current ISO 8601 datetime
- **STATUS**: "clean" when `issues_found=0`, `unresolved=0` and `critical_gaps=0`; otherwise "issues_open". Resolved findings still count in `issues_found`, so "issues_open" can mean mapped work, not a failed review.
- **unresolved**: this review's "Unresolved decisions" count; do not include prior reviews
- **critical_gaps**: number from "Failure modes: ___ critical gaps flagged"
- **issues_found**: total issues found across all review sections (Architecture + Code Quality + Performance + Test gaps)
- **MODE**: FULL_REVIEW for the Scope Challenge result "scope accepted as-is"; SCOPE_REDUCED for "scope reduced per recommendation".
- **COMMIT**: output of `git rev-parse --short HEAD`

## Review Readiness Dashboard

In finish step 4, read the review history and display the dashboard exactly as described in references/review-log.md ("Read the history" and "Review Readiness Dashboard").

## Next Steps — Review Chaining

In finish step 5, use the published dashboard to offer only applicable routes:
- **A) Run /gs-plan-ceo-review:** a significant product change has no CEO review.
  Mention it as an optional suggestion for new user-facing features, changed
  product direction or substantial scope expansion.
- **B) Ready to implement**

Note when an existing CEO review may be stale because this review found
contradictory assumptions or significant commit drift. If no additional review
is needed, state "All relevant reviews complete."

AskUserQuestion with only the applicable options. This is **navigation only**:
copy the working plan's task prerequisites, dependencies and execution order
without adding or strengthening them in the question or descriptions. A test
required before editing one function does not make every independent lane wait.
A next-step answer approves no implementation change.

For a substantive late change, follow the repeat path in finish step 5. Refresh
affected tasks, dependencies and parallelization along with the other outputs.
