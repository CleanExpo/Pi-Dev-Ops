# TODO choices, approval readiness, required outputs, report and navigation

Closing sequence steps 2-7 from references/review-sections.md.

## Resolve remaining TODO choices

### TODOS.md updates
**Keep the selected mode.** In HOLD SCOPE, a potential TODO must address an
evidenced gap in the accepted scope or its required correctness and operability.
Hypothetical future capacity, optional features, and alternatives to an adequate
approved remedy are expansions even when labeled TODOs; do not surface them in
HOLD SCOPE. Still audit observability and performance against the requirements,
and approve each real deferred gap individually. Expansion modes retain their
expansion scan and opt-in ceremony.

Only unanswered TODO proposals reach this menu. Do not ask again about an item
already deferred, skipped or kept; carry its actual answer and destination forward.
Resolve each remaining proposal through all four steps of 0D, using the menu
below. Keep its full comparison, saved question/options, Read-back and actual
answer. Never batch TODOs — one per question. If none remain, record that and continue.
Use the per-item format below.

For each TODO, describe:
* **What:** One-line description of the work.
* **Why:** The concrete problem it solves or value it unlocks.
* **Pros:** What you gain by doing this work.
* **Cons:** Cost, complexity, or risks of doing it.
* **Context:** Enough detail that someone picking this up in 3 months understands the motivation, the current state, and where to start.
* **Effort estimate:** Give separate human-team and CC S/M/L/XL labels.
  For a rough backlog estimate, start with S→S, M→S, L→M, XL→L. These are size
  categories, not time ratios. When work is decomposed into Implementation Tasks,
  estimate hours/minutes using that section's task-type ratios and actual work;
  use those estimates to refine the backlog labels.
* **Priority:** P1/P2/P3
* **Depends on / blocked by:** Any prerequisites or ordering constraints.

Then present options: **A)** Add to TODOS.md **B)** Skip — not valuable enough **C)** Keep in the current plan as required work, only when it is already part of accepted scope.

## Approval readiness

Check the decision ledger before Required Outputs. For each approved remedy:
1. Cite its actual answer, exact prior approval or preamble-authorized per-issue
   auto-decision. Setup, mode and navigation are not remedy approvals; an approach
   approves only its explicit commitments and their directly required tests.
2. Confirm that the plan applies only that answer's scope. Independent remedies
   and additional verification choices need their own rows and answers.
3. Keep declined, deferred and unanswered changes out of accepted work. An approved
   delivery-scope deferral is settled. Deferring a needed policy or remedy decision
   leaves that choice unresolved; show it in the final report.

If a draft lacks approval, mark it pending and use 0D; repeat this check after
its answer. No report or completion log is needed to run this check.

At the end of the six-column decision ledger, record `Approval readiness: PASS`
with the checked row IDs and their actual answer or approval references. Save or
present the updated plan under Step 0's storage policy, then continue to Required
Outputs. A substantive change invalidates this result; navigation alone does not.

## Required Outputs

Complete these three stages in order. They separate preparing review content from
announcing saved completion; no stage depends on a completion log written later.

### Stage 1 — Prepare the plan body and summary

Write the following sections, registries, diagrams, Markdown tasks and Completion
Summary in the working plan from approved changes. Keep them before the terminal
report. Task JSONL and approved TODOs use their specified paths, separate from the
0H CEO archive. The prepared summary supplies the report's current facts; it is
not yet a chat announcement of saved completion.

### Review facts

Derive facts from the approved ledger and completed sections: mode, findings,
unresolved choices, critical gaps, scope dispositions and each outside attempt's
coverage. Status is `clean` only with zero unresolved choices and critical gaps;
otherwise `issues_open`. No report or completion log is needed yet.

Use these facts in the Summary, report row and Review Log. Artifact cells stay
pending until confirmed writes, or not persisted when forbidden. A substantive
late decision repeats readiness and recomputes facts before refreshing outputs.

### "NOT in scope" section
List explicitly deferred and rejected work separately, with each actual answer
and one-line rationale. Deferred work also goes to TODOS.md; rejected work does not.

### "What already exists" section
List existing code/flows that partially solve sub-problems and whether the plan reuses them.

### "Dream state delta" section
Where this plan leaves us relative to the 12-month ideal.

### Error & Rescue Registry (from Section 2)
Match the approved review depth. For implementation-ready work, list every method
that can fail, its exception classes, rescue status/action and user impact.
For strategy-only work, use capability rows with failure mechanisms, user impact,
known safeguards, and an owner who must verify each unknown before implementation.
Do not invent method contracts. For one narrow decision, include only its dependencies.

### Failure Modes Registry
```
  CODEPATH | FAILURE MODE   | RESCUED? | TEST? | USER SEES?     | LOGGED?
  ---------|----------------|----------|-------|----------------|--------
```
Any row with RESCUED=N, TEST=N, USER SEES=Silent → **CRITICAL GAP**.
For strategy-only rows, CODEPATH names the capability; mark unknown rescue/test
coverage as unknown and name the verification owner. Count capability rows in the
Completion Summary; implementation-ready reviews count method/codepath rows.

### Scope Expansion Decisions (EXPANSION and SELECTIVE EXPANSION only)
For EXPANSION and SELECTIVE EXPANSION, reference the CEO plan's full 0G scope record
under the storage policy. List its dispositions without asking again:
* Accepted: {list items added to scope}
* Deferred: {list items sent to TODOS.md}
* Skipped: {list items rejected}

### Diagrams (mandatory, produce all that apply)
1. System architecture
2. Data flow (including shadow paths)
3. State machine
4. Error flow
5. Deployment sequence
6. Rollback flowchart

### Stale Diagram Audit
List every ASCII diagram in files this plan touches. Still accurate?

## Implementation Tasks

Turn findings into tasks within the approved review depth. Implementation-ready
tasks describe the build. Strategy-only tasks name the next research, design or
verification action and its owner; they do not choose implementation contracts.
List known files only. For unknown files, write "to be determined" and use an
empty JSONL files array. Each task needs a concrete verification step.
Always emit the markdown section. Write its JSONL artifact for `/gs-autoplan` only when the Step 0 storage policy permits it; otherwise label the complete task output not persisted and do not claim an aggregation artifact exists.

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
TASKS_FILE="$TASKS_DIR/tasks-ceo-review-$(date +%Y%m%d-%H%M%S).jsonl"
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)
BRANCH=$(git branch --show-current 2>/dev/null || echo unknown)
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"

# Repeat ONE jq invocation per task identified during this review.
# Substitute the placeholders inline with shell variables you set per task:
#   TASK_ID (T1, T2, ...), PRIORITY (P1/P2/P3), COMPONENT, TITLE,
#   SOURCE_FINDING, EFFORT_HUMAN, EFFORT_CC, FILES_JSON (a JSON array literal
#   like '["browse/src/sanitize.ts","browse/src/server.ts"]').
jq -nc \
  --arg phase 'ceo-review' \
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


### Completion Summary
Fill this template from Review facts now, as part of the plan body. Artifact
outcomes remain pending until their writes are confirmed. Stage 3 publishes it
after report verification; forbidden writes stay labeled not persisted.

Use the full mode name from Step 0E; replace spaces with underscores only in the
review log's `MODE` field. "System Audit" summarizes repository findings from
Step 0 and the review sections. "Lake Score" counts complete options selected:
Y is the number of answered coverage questions offering a 10/10 option; X is
how many selected that option. Report X/Y, excluding kind-only and unanswered
questions; use `N/A` when Y is zero.

```
  +====================================================================+
  |            MEGA PLAN REVIEW — COMPLETION SUMMARY                   |
  +====================================================================+
  | Mode selected        | [full mode name from Step 0E]               |
  | System Audit         | [key findings]                              |
  | Step 0               | [mode + key decisions]                      |
  | Section 1  (Arch)    | ___ issues found                            |
  | Section 2  (Errors)  | ___ error paths mapped, ___ GAPS            |
  | Section 3  (Security)| ___ issues found, ___ High severity         |
  | Section 4  (Data/UX) | ___ edge cases mapped, ___ unhandled        |
  | Section 5  (Quality) | ___ issues found                            |
  | Section 6  (Tests)   | Diagram produced, ___ gaps                  |
  | Section 7  (Perf)    | ___ issues found                            |
  | Section 8  (Observ)  | ___ gaps found                              |
  | Section 9  (Deploy)  | ___ risks flagged                           |
  | Section 10 (Future)  | Reversibility: _/5, debt items: ___         |
  | Section 11 (Design)  | ___ issues / SKIPPED (no UI scope)          |
  +--------------------------------------------------------------------+
  | NOT in scope         | written (___ items)                          |
  | What already exists  | written                                     |
  | Dream state delta    | written                                     |
  | Error/rescue registry| ___ rows, ___ CRITICAL GAPS                 |
  | Failure modes        | ___ total, ___ CRITICAL GAPS                |
  | TODOS.md updates     | ___ items proposed                          |
  | Scope proposals      | ___ proposed, ___ accepted (EXP + SEL)      |
  | CEO plan             | written / not persisted / skipped by mode  |
  | Outside voice        | provider + completed/unavailable/disabled/skipped |
  | Lake Score           | X/Y recommendations chose complete option   |
  | Diagrams produced    | ___ (list types)                            |
  | Stale diagrams found | ___                                         |
  | Unresolved decisions | ___ (listed below)                          |
  +====================================================================+
```

### Unresolved Decisions
If any AskUserQuestion goes unanswered, note it here. Never silently default.

### Stage 2 — Save and verify the terminal report

Use the prepared summary above, then follow this report procedure. Preserve the
complete body and summary before the report; no new body section follows it.

## Plan File Review Report

Produce the complete accepted plan and review output, including this report, under the Step 0 storage policy before announcing completion.

### Detect the plan file

Use an explicitly requested output/report file first. Otherwise use the reviewed plan named by the user, then the host active plan. Apply the Step 0 storage policy. Without a permitted file, produce the complete reviewed plan and report in chat, labeled not persisted; do not skip report generation.

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

For **Outside Review**, use this run's completed reviewer output and finding
dispositions: "N findings; R resolved; U unresolved". With no findings, write
"0 findings — completed review". Label native fallback findings as native and
keep external coverage unavailable. For disabled or unavailable attempts, write
the actual reason and "no completed external review"; never imply zero findings.
If prior history lacks counts, say "finding count not recorded". Preserve each
attempt's provider and outcome in OUTSIDE COVERAGE.

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

**Unresolved-decisions status (MANDATORY):** This is the report's final content,
after VERDICT. Count this review's open items from its ledger. For prior reviews,
sum `unresolved` over the latest fresh row per skill (the dashboard's seven-day
window), excluding the current skill so it is not counted twice.

- If both counts are zero, end with the exact unbolded line `NO UNRESOLVED DECISIONS`.
- Otherwise use the bold label `**UNRESOLVED DECISIONS:**` (not a new heading),
  then one bullet per current open item. When the prior count N is positive, add
  a final bullet `- + N unresolved from prior reviews`, even if there are no
  current items. The last bullet is the final non-whitespace line; append no
  separate count line or trailing prose. Never omit this status.


### Write to the plan file

If no destination is selected or writing is forbidden, assemble the same complete plan, review output and terminal report in chat, labeled not persisted. Do not run the file-writing steps below or claim their Read-back gate passed. Follow Stage 3's blocked chat return; no completed-review log or handoff. Otherwise save only accepted changes, keeping unresolved choices pending:

The report must always be the LAST section of the plan file — never mid-file.
Use a single delete-then-append flow:

1. Read the existing plan/report, if present. Preserve its content and apply only
   accepted changes; include the full review output. Locate any existing
   `## GS REVIEW REPORT` section.
2. If found, use the Edit tool to DELETE the entire existing section. Match from
   `## GS REVIEW REPORT` through either the next `## ` heading or end of
   file, whichever comes first. Replace with the empty string. This applies
   regardless of where the section currently lives — mid-file deletion is
   intentional, not a special case. If the Edit fails, report the error and stop before Review Log or decision logging.
3. Save the complete updated plan and review body with the new
   `## GS REVIEW REPORT` at EOF:
   - If the destination file exists, Read it now, whether or not step 2 deleted
     a report. Use Edit with the suffix from this Read, or Write the complete file.
   - If the destination file does not exist, use Write to create the complete file.
   In both cases, keep the report last and continue to the Read-back gate.
4. **Read-back gate:** Read the saved file. Verify the accepted changes, full review
   output, current review row, verdict and final unresolved-decisions status, with
   `## GS REVIEW REPORT` as the last section. If writing or verification fails,
   report the error and stop before Review Log or decision logging.

Do NOT replace the section in place; delete it and append the new report at EOF.

### Stage 3 — Publish the Completion Summary

**Publish the Completion Summary:** After the report Read-back gate passes, show
the prepared summary in chat with confirmed artifact outcomes. Do not append it
after the report in the file. If no plan/report write is permitted, show the
complete plan, report and summary as not persisted, then use **Gate outcome:
Blocked**. This delivers the review content without claiming saved completion;
skip Review Log and the next-skill handoff.

## Handoff Note Cleanup

After producing the Completion Summary, remove this branch's handoff notes only if the storage policy permits cleanup. Otherwise retain them and report that cleanup was not performed.

```bash
setopt +o nomatch 2>/dev/null || true  # zsh compat
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
rm -f ~/.local/state/gs/projects/$SLUG/*-$BRANCH-ceo-handoff-*.md 2>/dev/null || true
```

## Review Log

Attempt these history writes only after the plan/report's successful write and
Read-back. A failed plan/report save or verification stops before this block.
If metadata writes are forbidden, skip these commands and show their actual
fields in chat as **not persisted**.

The history command below is best-effort under Step 0's **Artifact outcomes**
policy. If one fails, retain its diagnostic, show its actual unsaved fields and
continue; do not claim that entry was recorded. Display the dashboard from saved
history, clearly identifying this run as unlogged when its review-log write failed
or was forbidden. This differs from 0H's required spec-metrics write.
This payload omits the dashboard's optional `plan_sha256`: use age for freshness
without claiming a content match when no hash was recorded.

Substitute these values from the Completion Summary before running the commands:
- **TIMESTAMP**: current UTC ISO 8601 datetime (e.g., 2026-03-16T14:30:00Z)
- **STATUS**: "clean" if 0 unresolved decisions AND 0 critical gaps; otherwise "issues_open"
- **unresolved**: number from "Unresolved decisions" in the summary
- **critical_gaps**: number from "Failure modes: ___ CRITICAL GAPS" in the summary
- **MODE**: the mode the user selected (SCOPE_EXPANSION / SELECTIVE_EXPANSION / HOLD_SCOPE / SCOPE_REDUCTION)
- **scope_proposed**: number from "Scope proposals: ___ proposed" in the summary (0 for HOLD/REDUCTION)
- **scope_accepted**: number from "Scope proposals: ___ accepted" in the summary (0 for HOLD/REDUCTION)
- **scope_deferred**: number of items deferred to TODOS.md from scope decisions (0 for HOLD/REDUCTION)
- **COMMIT**: output of `git rev-parse --short HEAD`

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
echo '{"skill":"plan-ceo-review","timestamp":"TIMESTAMP","status":"STATUS","unresolved":N,"critical_gaps":N,"mode":"MODE","scope_proposed":N,"scope_accepted":N,"scope_deferred":N,"commit":"COMMIT"}' >> "$GS_PROJ/$BRANCH-reviews.jsonl" && echo LOGGED || echo "NOT PERSISTED"
```

## Review Readiness Dashboard

After completing the review, read the review history and display the dashboard exactly as described in references/review-log.md ("Read the history" and "Review Readiness Dashboard").

## Next Steps — Review Chaining

After displaying the Review Readiness Dashboard, recommend the next review(s) based on what this CEO review discovered. Read the dashboard output to see which reviews have already been run and whether they are stale.

**Recommend /gs-plan-eng-review if eng review is not skipped globally** — check the dashboard output for `skip_eng_review`. If it is `true`, eng review is opted out — do not recommend it. Otherwise, eng review is the required shipping gate. If this CEO review expanded scope, changed architectural direction, or accepted scope expansions, emphasize that a fresh eng review is needed. If an eng review already exists in the dashboard but the commit hash shows it predates this CEO review, note that it may be stale and should be re-run.

gstack's /plan-design-review is not adopted here; if UI scope was detected, note it and leave a design pass to the user.

Use AskUserQuestion to present the next step. Include only applicable options:
- **A)** Run /gs-plan-eng-review next (required gate)
- **B)** Skip — I'll handle reviews manually

## docs/designs Promotion (EXPANSION and SELECTIVE EXPANSION only)

At the end of the review, if the vision produced a compelling feature direction, offer to promote the CEO plan to the project repo. AskUserQuestion:

"The vision from this review produced {N} accepted scope expansions. Want to promote it to a design doc in the repo?"
- **A)** Promote to `docs/designs/{FEATURE}.md` (committed to repo, visible to the team)
- **B)** Keep in `~/.local/state/gs/projects/` only (local, personal reference)
- **C)** Skip

If promoted and those writes are permitted, copy the CEO plan content to `docs/designs/{FEATURE}.md` (create the directory if needed) and update the original CEO plan's `status` from `ACTIVE` to `PROMOTED`. Otherwise present the proposed design document in chat, marked not persisted; do not claim promotion occurred.

## Return

These review tasks are finished without changing the plan. Return to this skill's
main `SKILL.md` at **Section self-check** for terminal verification.
