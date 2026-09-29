# Step 0 — Nuclear Scope Challenge + Mode Selection

Read this file in full at SKILL.md Step 0. "The preamble" means references/askuserquestion-format.md.

## Step 0: Nuclear Scope Challenge + Mode Selection

Startup:
1. Choose the review depth and artifact destinations, then open the ledger below.
2. Record 0A–0C evidence; call 0D only for a required approach choice.
3. Select the mode in 0E and follow its route table.
4. Complete Review Sections and its closing sequence; return to Section self-check.

0D is reusable, not an unconditional question. Observations do not approve changes.

**Set review depth from the user's request.** Default to implementation-ready.
Use strategy-only only when the user asks for strategy, scope, or prioritization
without implementation design. Use one narrow decision only when the user names a
single choice. To expand strategy-only into implementation design, use 0D with
**A)** Keep this review strategy-only **B)** Add implementation design for the
named capability. Recommend A unless a concrete blocker requires B; wait for the
answer. B permits design detail for that capability only.
Resolve a choice only when output would be wrong without it, a blocker would be
hidden, or scope would change. Reuse prior answers only for the same scope.

Plain terms:
- **Required choice:** a mode, scope, deferral, TODO, spec, outside-review or
  finding decision needed before the next step.
- **Pending:** recorded in the ledger and waiting for approval.
- **Settled:** answered by the user, directly instructed, or auto-authorized by
  the preamble.

Review depth controls the detail within each section. Review Sections 1–10 in every depth;
run Section 11 only for UI. Strategy-only uses capability-level rows and
"implementation owner must prove ___" notes, including the Error & Rescue map.
Implementation-ready names interfaces, codepaths, rescue behavior and tests.
For one narrow decision, apply every section to that choice and its dependencies.

**Keep the stated limits.** Record each measure, value, unit and prerequisite. Count all deliverables, including reused code. Changing a limit needs evidence and user approval.

**Storage policy: choose before writing.** Honor user/host artifact and cleanup
limits. One working plan: requested output, else reviewed plan, else host active
plan. Use native Write for a missing file and scoped Edit for checkpoints;
retain all current content, ledger rows and comparisons.

**Artifact outcomes:** Never claim an unconfirmed save, read-back or log.
When writing is forbidden, continue analysis and decisions without writing.
Present complete artifacts as **not persisted**. At finalization, an unsaved
plan/report means **completion blocked**: no completion log, ExitPlanMode or next-skill
handoff.

| Permitted write | On failure |
|---|---|
| Plan/report, CEO summary, approved TODOs and tasks | Stop with the cause; chat cannot replace a failed save. Missing jq may omit only task JSONL, as the task instructions explain. |
| 0H spec-review metrics | Stop with the cause; reviewer availability does not waive this write. |
| Review, decision and question history logs | Report cause and unsaved fields; continue. The plan's ledger is still required. |

Paths: CEO archive = `CEO_PLANS` (0H), tasks =
`~/.local/state/gs/projects/`, metrics = `~/.local/state/gs/analytics/`; review history per references/review-log.md.

Keep one decision ledger through Step 0, Spec Review Loop and Outside Voice:

| ID and owner | Contract and evidence | Current | Proposed | Status | Exact approval and scope |
|---|---|---|---|---|---|

Name owners; cite evidence, conventions and tests; mark unknowns. Current holds approved values; Proposed holds alternatives. Status: unresolved, approved, reopened, deferred or declined. Cite actual instructions/answers and exact scope.

### 0A. Premise Challenge
Name the real problem, target outcome and do-nothing cost. Say whether the plan
solves the pain directly or only a proxy.

### 0B. Existing Code Leverage
Map each sub-problem to reusable code. For any rebuild, explain why refactoring
the existing path is worse.

### 0C. Dream State Mapping
Describe the 12-month ideal and whether this plan moves toward it.
```
  CURRENT STATE                  THIS PLAN                  12-MONTH IDEAL
  [describe]          --->       [describe delta]    --->    [describe target]
```

Before 0E, call 0D for unresolved approaches: A) current/requested plan,
B) smallest scoped alternative, C) larger approach/rewrite only with evidence.
With no required choice, or after those choices settle, go to 0E.

### 0D. Alternatives (reusable decision procedure)

**Choose the question's route first:**
- **Admin question:** mode, setup, navigation, document approval or promotion.
  Use its listed menu and the preamble question transport, then wait and record
  the answer. Skip steps 1–4; this approves no plan changes.
- **Plan decision:** review-depth expansion, scope additions/cuts, approach
  choices, TODOs, specs and review/outside findings. Start at step 1. Reuse exact
  prior approvals; run steps 2–4 only when a new answer is needed, even for one option.

If an admin answer requests a plan change, use the Plan decision route for that
change. 0D never restarts mode selection.

**1. Check sources and prior answers.**
Compare input, source and answers; correct facts, flag conflicts and preserve unknowns.
Reuse exact approvals. Reopen only for contradictions, changed assumptions or
user instructions, never speculation or reviewer agreement. With no new answer
needed, cite settled answers and return; invent no alternatives or approval.

**2. Record the pending choice.**
Give independent changes separate ledger rows; explain necessary coupling. Record
owner, behavior, limits, test method and coverage in Current/Proposed. Cite the
source filename/message and section/lines when available.

| Test choice | Treatment |
|---|---|
| Code change and required regressions | Keep together; carry both forward once approved. |
| Approved change with open test method/coverage | Decide once; every option preserves required behavior and approved tests. |
| Tests for existing behavior | Separate independently selectable additions. Tests for undecided behavior stay pending. |

Record pending rows before comparisons; never prewrite approval or tasks.

**3. Compare and save that row's options.**
Build one `currentDecision` using these fields and the preamble format:

| Field | Required content |
|---|---|
| `question` | Full brief: `D<N> — <ROW-ID>: <one-line question>`, Project, ELI10, Stakes, Recommendation and applicable completeness/net text. D counts questions; ROW-ID identifies the pending choice. |
| `header` and option labels | Final native text within host limits; exactly one label includes `(recommended)`. |
| Each option's `description` | A 1–2 sentence summary; S/M/L/XL effort, low/medium/high risk, reuse, verification coverage, at least 2 ✅ pros and 1 ❌ con. Apply the preamble's minimum lengths and destructive-choice exception. |

Without a prescribed menu, offer 2–3 options (prefer 3 for non-trivial plans).
For an option with no implementation, use effort S and state zero implementation
work, never effort 0. Weigh diff size and long-term architecture equally, including rewrites.

In Proposed, compare every commitment in the labels, descriptions and pros/cons:

```text
Commitment | Source/approval or pending | Current | A | B | C
```

Include one column per option (add D for a four-option menu). Show unchanged,
shared and pending values. Changes remain separate decisions even if they use the same framework.
Keep other rows fixed or pending; preserve requirements, tests and fixes.

Score this row's coverage differences: 10 = all edge cases, 7 = happy path,
3 = shortcut. For different kinds of work, write:
"Note: options differ in kind, not coverage — no completeness score."

**Pre-question checkpoint:** Validate every field above before saving.
Find exactly one row by its assigned ID; verify owner, Current/Proposed, Status
and Exact approval and scope. Repair missing/duplicate rows in step 2.
Effort/risk must each be one listed value, never a range. Correct missing or
invalid fields and host-limit violations before saving.

- **Save.** Under the storage policy, save/present the complete current plan,
  pending rows and comparisons. Copy the grid and all exact fields below,
  without the illustrative fence delimiters:

  ```text
  ## currentDecision (ROW-ID)
  Commitment comparison: <complete grid>

  Question: <complete currentDecision.question>
  Header: <exact currentDecision.header>
  A) <exact first option label>
  <full first option description>
  B) <exact second option label>
  <full second option description; repeat for all offered options>
  ```

  Replace the whole payload on revision.
  Keep answered decisions and their answers under separate headings.
- **Read-back.** After the latest successful Write/Edit, Read the ledger row and
  full payload through the last option's description; fetch continuations.
  Verify IDs and fields against `currentDecision`, citations against source.
  Read despite Edit's current-in-context hint. For chat, verify the complete text
  labeled **not persisted**. A grid, summary or pointer is insufficient.

A failed save stops the review. Correct mismatches, save and Read again before dispatch.

**4. Ask, record the answer, and amend.**
Copy the verified Read or chat text into one native arguments object:
`{questions: [{question, header, options: [{label, description}, ...]}]}`.
Compare its question, header, labels and full descriptions literally with the
verified fields, ignoring only saved selector prefixes such as `A)` or `B)`.
Compare strings, not format/scores. Changes repeat step 3's save and Read-back.
Ask one row per call with that object unchanged, without recomposing.
Only the preamble can authorize prose or auto-decision transport.

**STOP for the actual answer, even for a lone option.** Only a preamble-authorized
auto-decision resolves this wait; record its authority. Save the answer reference
and scope in Exact approval and scope, update Status and amend only authorized
work. A recommendation is not approval; do not edit code.

**Post-answer checkpoint:** Save or present the complete amended plan under the
storage policy before taking another row.

If all options are declined, continue only with a viable current approach retained
by the answer; otherwise leave the row unresolved and stop for direction.

Return to the calling step with the saved answer; do not ask it again.
Record findings even after resolution; say "No issues, moving on." only with none.

### 0E. Mode Selection
Follow the AskUserQuestion format in references/askuserquestion-format.md.

1. An explicit choice skips steps 2–3. "Go big", "ambitious" or "cathedral" means SCOPE EXPANSION; "hold scope but tempt me", "show me options" or "cherry-pick" means SELECTIVE EXPANSION. Do not ask again.
2. Recommend without selecting. Count distinct planned file additions, edits and deletions, labeling estimates. For >15 planned changed files, recommend SCOPE REDUCTION. Otherwise: a new product/system (greenfield) → SCOPE EXPANSION; added capability → SELECTIVE EXPANSION; fix/refactor → HOLD SCOPE. If categories overlap or are unclear, explain why and recommend HOLD SCOPE; step 3 still resolves the choice.
3. Resolve that recommendation. Offer all four modes in one AskUserQuestion,
   using step 2's recommendation. **STOP for the answer**; the user's choice
   wins. These modes differ in kind, not coverage; do NOT score completeness.

4. **Mode handoff:** After selection, send brief chat before tools or further questions. Explain the mode's application and rationale. Include every governing approved row's ID, answer reference and accepted scope; do not collapse several choices into one approach.
- Selection message: `Mode: <selected mode>; approved decisions: <rows or none>. <Application and rationale>.`

Record mode provenance after the handoff:
- **Explicit user choice:** instruction and selected mode; no question log because none was asked.
- **Actual question answer:** question, answer reference and mode.

If 0D needed no new choice, say "No new approach decision was needed". Ask before changing the mode.

Selecting a mode does not approve changes. Preserve 0D approvals and ask about
each proposed addition or cut, including those prompted by file-count thresholds.

Follow the selected mode's route:

| Mode | Remaining Step 0 work |
|------|----------------------|
| SCOPE EXPANSION / SELECTIVE EXPANSION | 0F → 0G → 0H (including its spec review loop) → 0I |
| HOLD SCOPE | 0G → 0I |
| SCOPE REDUCTION | 0G |

After this route, continue to Review Sections for the full review, outputs and report.

### 0F. Expansion Framing (shared by EXPANSION and SELECTIVE EXPANSION)

Prepare pending candidates for 0G: user experience, concrete addition, S/M/L/XL
effort, risk and impact. Explain ambition enthusiastically in SCOPE EXPANSION;
balance benefits and tradeoffs without unsupported promises in SELECTIVE
EXPANSION. Mark one option `(recommended)` when presenting choices; this label
does not approve scope. The user decides each proposal in 0G.

### 0G. Mode-Specific Analysis
In expansion modes, extend 0F's pending list with this analysis, then resolve
each proposal individually.

**For SCOPE EXPANSION:**
1. **10x check:** Describe 10x value for 2x effort.
2. **Platonic ideal:** What would the best engineer with unlimited time and perfect taste build? Start with the user's experience.
3. **Delight scan:** List at least 5 adjacent 30-minute improvements that would delight the user.
4. **Expansion opt-in ceremony:** Present visions and individual proposals; enthusiastically explain each one's value. The user decides.

**For SELECTIVE EXPANSION:**
1. Run all three HOLD SCOPE checks below, including their defer/keep decisions.
2. Describe 10x ambition, run the delight scan and assess platform potential. Candidates stay pending until scope answers.
3. **Cherry-pick ceremony:** Use 0F with S/M/L/XL effort and risk. For more than 8, present the top 5–6; offer the rest on request.

For both expansion modes, ask separately for each addition: **A)** Add to this plan's scope **B)** Defer to TODOS.md **C)** Skip. Accepted items govern the remaining sections.

**For HOLD SCOPE** — run this:
1. Complexity check: at more than 8 files or more than 2 new classes/services, challenge whether fewer moving parts achieve the same goal.
2. Find the minimum changes for the goal; flag work deferrable without blocking it.
3. Keep stated invariants and acceptance criteria; repairs needed to meet them are in scope.

**For SCOPE REDUCTION:** propose minimum scope and resolve each proposed deferral
with the defer/keep menu below; retain the rest.

**Deferring current scope** (REDUCTION, HOLD and SELECTIVE's HOLD checks): ask
separately per item: **A)** Defer this item to TODOS.md **B)** Keep it in scope.

Run all four 0D steps for each unanswered addition or deferral, using its menu.
These scope choices differ in kind; do not score completeness. Keep other scope
fixed or pending; wait for the answer before applying it.
A deferral changes only delivery scope: record its answer/reason beside the prior
approval. Keep other approvals and limits unchanged. In later sections, review
the retained work and accepted additions; list deferred or rejected work as excluded.

Save dispositions under the storage policy:
- **Add / Keep:** accepted working-plan scope.
- **Defer:** TODOS.md with context and NOT in scope with the deferral reason. This postpones work; it does not reject it.
- **Skip / Cut:** NOT in scope with the rejection reason; no TODO.

Reuse answered scope decisions without another question or comparison. Inclusion
does not settle pending implementation choices; keep those rows visible.

### 0H. Persist CEO Plan (EXPANSION and SELECTIVE EXPANSION only)

Prepare the full amended working plan and a separate CEO scope summary. Keep
behavior, requirements and scope consistent; the summary cannot serve as the plan.

**Save or present both inputs under the storage policy.** For permitted storage:

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
CEO_PLANS="$GS_PROJ/ceo-plans"
mkdir -p "$CEO_PLANS"
echo "CEO_PLANS=$CEO_PLANS"
```

Use `{printed CEO_PLANS}/{YYYY-MM-DD}-{feature-slug}.md`. Archiving old (>30 days) or merged/deleted-branch plans requires approval.

**Otherwise:** Present both inputs in full as not persisted.

**CEO summary format — use for both saved and chat output:**

```markdown
---
status: ACTIVE
---
# CEO Plan: {Feature Name}
Generated by /gs-plan-ceo-review on {date}
Branch: {branch} | Mode: {EXPANSION / SELECTIVE EXPANSION}
Repo: {owner/repo}

## Plan under review
{working plan path, or "Working plan — complete text in chat; not persisted"}

## Vision

### 10x Check
{10x vision description}

### Platonic Ideal
{platonic ideal description — EXPANSION mode only}

## Scope Decisions

| # | Proposal | Effort | Decision | Reasoning |
|---|----------|--------|----------|-----------|
| 1 | {proposal} | S/M/L/XL | ACCEPTED / DEFERRED / SKIPPED | {why} |

## Accepted Scope (added to this plan)
- {bullet list of what's now in scope}

## Deferred to TODOS.md
- {items with context}
```

#### Spec Review Loop

Run an adversarial review before presenting the final document to the user.
Use 0D for any new or reopened amendment discovered by the reviewer. The later 0H approval approves only the completed working plan and CEO summary, not unresolved amendments.

**Step 1: Dispatch reviewer subagent**

Read Agent's tool definition. Set `run_in_background: false` if that field is available; omit it otherwise. Launch one reviewer with both inputs below.

If the result contains a completed review, consume it. If it returns a pending task, use the host's wait tool. With no wait tool, end this response and resume on its completion notification. While waiting, do not advance, edit either input or launch another reviewer.

Prompt the subagent with:
- Both saved absolute paths, or both complete labeled texts if either input is not persisted: CEO scope summary and current amended working plan. No other conversation context.
- "Read both inputs in full. Evaluate them together on all five dimensions.
  Flag contradictions, unsupported accepted expansions and required behavior
  missing from both. Cite input and requirement for each finding. If either
  input is unavailable or incomplete, report that failure instead of grading
  partial input."

**Dimensions:**
1. **Completeness** — requirements and edge cases.
2. **Consistency** — no contradictions.
3. **Clarity** — implementable without follow-up questions.
4. **Scope** — no unapproved creep or YAGNI.
5. **Feasibility** — buildable with the stated approach.

The subagent should return:
- A quality score (1-10) across all dimensions
- For each dimension, PASS or numbered issues with suggested fixes. Overall PASS only if all dimensions pass.

**Step 2: Process the result**

- **Unavailable:** If launch or review fails, times out, or cannot review both complete inputs, stop the loop. Say "Spec review unavailable — presenting unreviewed doc." Preserve the failure and all prior findings. Continue to Step 3 to record the unavailable outcome; a successful reviewer result is not required.
- **PASS:** Stop the loop.
- **Issues:** Stop after the third review, or when consecutive reviews repeat the same unresolved issues (the same requirements and problems). Otherwise use 0D for new or reopened choices, amend the working plan and CEO summary under the storage policy, Keep both consistent, and re-dispatch with both updated inputs and the same instructions.

Make at most three reviewer launches. A missing score alone does not require another review.

**Step 3: Report and persist metrics**

Report the outcome and fields below. Show full reviewer output on request. List unresolved issues under "## Reviewer Concerns" in the CEO summary, citing the owning input.

SCORE is the latest attempt's reported 1–10 grade after reviewing both full inputs. For an unavailable review or missing/invalid grade, use JSON `null` ("score unavailable"). Label earlier grades "prior review score".

Recording the **0H spec-review metrics** is
required when writing is permitted, even if the reviewer failed. Append the
actual outcome below; failed mkdir or append stops the review. When writing is
forbidden, show the actual fields as not persisted and continue without writing.
Reviewer failure therefore continues here; required storage failure stops here.
```bash
mkdir -p ~/.local/state/gs/analytics || exit 1
echo '{"skill":"plan-ceo-review","ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","iterations":ITERATIONS,"issues_found":FOUND,"issues_fixed":FIXED,"remaining":REMAINING,"quality_score":SCORE}' >> ~/.local/state/gs/analytics/spec-review.jsonl || exit 1
```
ITERATIONS counts actual reviewer launches. FOUND, FIXED and REMAINING count reported issues, reviewer-confirmed fixes and reported unresolved issues. Use actual counts, never estimates.

After the loop completes or reports unavailable, present both inputs for final
scope-document approval. Ask with the preamble question transport:
**A)** Approve these documents and continue to 0I **B)** Revise these documents
**C)** Pause this review. Recommend A only if both reflect the exact decisions.
Wait and record the answer. A accepts these document versions only; unresolved
amendments and implementation remain unapproved. For B, resolve the requested
changes through 0D, update both inputs and repeat document approval. C stops.
After A, run 0I before Review Sections.

### 0I. Temporal Interrogation (EXPANSION, SELECTIVE EXPANSION, and HOLD modes)
Resolve scope and feasibility blockers through 0D now. Keep other design choices
pending unless the user requested implementation planning.
```
  HOUR 1 (foundations):     What does the implementer need to know?
  HOUR 2-3 (core logic):   What ambiguities will they hit?
  HOUR 4-5 (integration):  What will surprise them?
  HOUR 6+ (polish/tests):  What will they wish they'd planned for?
```
Save the sequence, feasibility blockers and pending choices in the plan, with human-team and CC effort.

Carry the ledger and each answer's exact scope into the review sections.
