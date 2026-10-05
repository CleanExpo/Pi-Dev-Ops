# Phase 4: Final Approval Gate + Completion

Read after `references/tasks-aggregator.md` has set `$AGGREGATED_TASKS`.

**STOP here and present the final state to the user.**

Present this message, then use AskUserQuestion (format:
`references/askuserquestion-format.md`):

```
## /gs-autoplan Review Complete

### Plan Summary
[1-3 sentence summary]

### Decisions Made: [N] total ([M] auto-decided, [K] taste choices, [J] user challenges)

### User Challenges (both models disagree with your stated direction)
For each: **Challenge [N]: [title]** (from [phase]); You said: [original];
Both models recommend: [change]; Why: [reasoning]; What we might be missing:
[blind spots]; If wrong: [cost]. If security/feasibility, say both models flag
that risk. Your original direction stands unless you explicitly change it.

### Your Choices (taste decisions)
For each: **Choice [N]: [title]** (from [phase]). Recommend [X] — [principle].
Name the viable alternative and its downstream impact.

### Auto-Decided: [M] decisions [see Decision Audit Trail in plan file]

### Review Scores
CEO and Eng: phase summary plus Codex, Claude subagent and consensus status.
Design and DX: not reviewed (not adopted in this library).

### Cross-Phase Themes
List concerns independently raised in 2+ phases. If none: "No cross-phase themes — each phase's concerns were distinct."

### Deferred to TODOS.md
[Items auto-deferred with reasons]

### Implementation Tasks (aggregated across phases)
[Substitute $AGGREGATED_TASKS. If empty: "_No per-phase task lists found in $TASKS_DIR for branch $BRANCH._"]
```

**Cognitive load:** skip empty User Challenges / Your Choices. Use a flat list
for 1-7 taste decisions; group 8+ by phase and warn that ambiguity is high.

AskUserQuestion options (recommend A when there are no User Challenges and no
incomplete items; recommend B2 when User Challenges exist):
- A) Approve as-is
- B) Approve with overrides
- B2) Resolve user challenges
- C) Interrogate
- D) Revise
- E) Reject

The cap is 4 options per call: batch A/B/B2 as the approve group and C/D/E as the
continue-working group, or split per the format reference. Never drop an option.

**Option handling:**
- A: mark APPROVED, write review logs (below), suggest implementation as the next step
- B: ask which overrides, apply, then follow D's affected-phase rerun rule (including Eng last) before re-presenting the gate. Counts toward the same 3-cycle cap as D.
- B2: accept/reject User Challenges one at a time; rejected ones preserve the user's direction. Re-run Eng, then re-present the gate.
- C: answer freeform, re-present gate
- D: make changes, re-run affected phases (scope→1, test plan→3, arch→3; a re-run of Phase 1 re-runs Eng after it — the gate always reviews the final plan). Max 3 cycles.
- E: start over

**Starting an affected-phase rerun:** Keep the current Implementation plan and all
prior accepted obligations intact. Create a fresh amendment checkpoint
(references/snapshot.md, section C). Carry forward unchanged accepted requirements.
Never replay old replacements. This starts a new phase invocation; compaction resumes
the existing invocation and checkpoint. Eng still runs last.

---

## Completion: Write Review Logs

On approval, log each completed review to the shared review history
(`~/.claude/skills/gs-plan-eng-review/references/review-log.md`). Replace STATUS and N
with actual phase values. STATUS is "clean" or "issues_open".

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
COMMIT=$(git rev-parse --short HEAD 2>/dev/null)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
L="$GS_PROJ/$BRANCH-reviews.jsonl"
echo '{"skill":"plan-ceo-review","timestamp":"'"$TIMESTAMP"'","status":"STATUS","unresolved":N,"critical_gaps":N,"mode":"SELECTIVE_EXPANSION","via":"autoplan","commit":"'"$COMMIT"'"}' >> "$L" &&
echo '{"skill":"plan-eng-review","timestamp":"'"$TIMESTAMP"'","status":"STATUS","unresolved":N,"critical_gaps":N,"issues_found":N,"mode":"FULL_REVIEW","via":"autoplan","commit":"'"$COMMIT"'"}' >> "$L" && echo LOGGED || echo "NOT PERSISTED"
```

Dual voice logs: write one record per PHASE (`ceo`, `eng`) with that phase's
status/counts. Generate one AUTOPLAN_RUN_ID and share it with TIMESTAMP.
```bash
echo '{"skill":"autoplan-voices","run_id":"AUTOPLAN_RUN_ID","timestamp":"'"$TIMESTAMP"'","status":"STATUS","source":"SOURCE","host":"claude","outside_provider":"codex","outside_status":"OUTSIDE_STATUS","phase":"PHASE","via":"autoplan","consensus_confirmed":N,"consensus_disagree":N,"commit":"'"$COMMIT"'"}' >> "$L"
```

SOURCE = "codex" only for completed external output; native results use "in-host".
OUTSIDE_STATUS is completed, unavailable, disabled or skipped. Never carry success
across phases/runs.

Present a phase coverage table (CEO, eng; design and DX "not adopted"): host, outside
provider/status, native completion, findings, and partial coverage. Replace N with
actual counts.

Report completion status: DONE (approved, all required outputs present),
DONE_WITH_CONCERNS (approved with warned incomplete items or open taste choices),
BLOCKED (a phase could not complete; name it and what was tried), or NEEDS_CONTEXT
(the gate is awaiting the user's answer).
