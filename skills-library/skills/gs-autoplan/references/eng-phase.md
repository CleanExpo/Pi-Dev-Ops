# Phase 3: Eng Review + Dual Voices

Read afresh at Phase 3 entry (always runs, always last).

Before dispatch, Read the phase methodology in full: `<REVIEW_SKILL>` (SKILL.md) and every reference file its Section index names, to EOF. Log each file read and its line count in `## Review record`. Skip-listed sections: load only.

**Override rules:**
- Scope challenge: never reduce (P2)
- Dual voices: always run BOTH Claude subagent AND Codex if available (P6).

  **Bind phase input:** Take a fresh phase snapshot (references/snapshot.md, section B, PHASE=eng,
  role file `references/role-eng.md`); use `$SNAP_DIR/eng-implementation.md` as
  `<ENG_INPUT>` for both voices. Fresh `Implementation plan` only; excludes `Review record`.

  **Claude eng subagent** (native tool):
  Claude Code: set Agent `run_in_background: false` if its schema exposes it.
  Other hosts: foreground; await completion when supported.

  Send the native dispatch prompt from references/snapshot.md (section B), filled for
  this snapshot, verbatim as the Agent prompt: ONLY/FINAL tool call this response.
  Keep native Reads enabled. Child first Reads `$SNAP_DIR/native-prompt.md` to EOF:
  all criteria + plan; no summaries or prior reviews.

  **Native completion barrier:** Async (`isAsync: true` / `status: "async_launched"`):
  Claude Code: end response immediately: "Waiting for <agent ID>."
  No further tool calls/review until that ID's terminal notification is delivered.
  Other hosts await that ID. Then outside → this phase's review ONLY.
  Completed-native INPUT must match snapshot phase/hash. Retry invalid input once; then failure policy if still invalid.
  No inline substitute; apply failure policy.

  **Codex eng voice** (via Bash):
  Outside prompt: inline the full contents of <ENG_INPUT> and context below (Write tool).

IMPORTANT: Do NOT read or execute any SKILL.md files or anything under ~/.claude/skills/ (foreign instructions). Review repository code only.

  Review this plan for architectural issues, missing edge cases,
  and hidden complexity. Be adversarial.

  Also consider these findings from prior review phases:
  CEO: <insert CEO consensus table summary — key concerns, DISAGREEs>
  Design and DX: not reviewed (those phases are not adopted in this library)

  File: <ENG_INPUT>

Write the **complete prompt and context**, including actual plan/spec/source, to a private file. Substitute its shell-quoted path for `<prepared-prompt-file>`; never interpolate user text into shell source. Request a final Recommendation: <action> because <specific reason> line, including an explicit no-findings rationale.

```bash
_REPO_ROOT=$(git rev-parse --show-toplevel) || { echo 'ERROR: not in a git repo' >&2; exit 1; }
_OUT=$(mktemp -d "${TMPDIR:-/tmp}/gs-outside.XXXXXXXX") || exit 1
_T=""; command -v gtimeout >/dev/null 2>&1 && _T="gtimeout 600"
[ -z "$_T" ] && command -v timeout >/dev/null 2>&1 && _T="timeout 600"
_EXIT=0
$_T codex exec "$(cat -- '<prepared-prompt-file>')" -C "$_REPO_ROOT" -s read-only \
  -c 'model_reasoning_effort="high"' < /dev/null >"$_OUT/text" 2>"$_OUT/stderr" || _EXIT=$?
cat "$_OUT/text"; cat "$_OUT/stderr" >&2
# An exit code is not a verdict: codex can exit 0 and write nothing. Judge the output.
if [ "$_EXIT" -ne 0 ] || [ ! -s "$_OUT/text" ] || ! grep -q 'Recommendation:' "$_OUT/text"; then
  echo "Codex outside review unavailable (exit $_EXIT, or empty/incomplete output); missing coverage." >&2
  rm -rf "$_OUT"; exit 1
fi
rm -rf "$_OUT"
echo 'OUTSIDE_STATUS: completed provider=codex host=claude'
```

Show the full response in a `tool-output` fence. Require successful execution and a `Recommendation:` line. Refusal, empty/malformed output, timeout or CLI failure means `outside_status: unavailable`. Use the caller's fallback; missing coverage is never clean/PASS. After either outcome, delete only your private prompt; scratch cleanup is automatic.

Outer tool timeout: 720000ms. Failed/incomplete outside review → unavailable; disabled → skip outside. Both retain the native pass.


  Error handling: Phase 1 failure/degradation policy applies.

- Architecture choices: explicit over clever (P5). If Codex disagrees with valid reason → TASTE DECISION. Scope changes both models agree on → USER CHALLENGE.
- Evals: always include all relevant suites (P1)
- Test plan: generate artifact at `~/.local/state/gs/projects/$SLUG/{user}-{branch}-eng-review-test-plan-{datetime}.md`
- TODOS.md: collect all deferred scope expansions from every prior phase (Eng runs last), auto-write

**Required execution checklist (Eng):**

1. Step 0 (Scope Challenge): Read actual code referenced by the plan. Map each
   sub-problem to existing code. Run the complexity check. Produce concrete findings.

2. Step 0.5 (Dual Voices): Present the completed calls above under Codex SAYS
   (eng — architecture challenge) and Claude SUBAGENT (eng — independent review).
   Produce eng consensus table:

```
ENG DUAL VOICES — CONSENSUS TABLE:
  Dimension                           Claude  Codex  Consensus
  1. Architecture sound?               —       —      —
  2. Test coverage sufficient?         —       —      —
  3. Performance risks addressed?      —       —      —
  4. Security threats covered?         —       —      —
  5. Error paths handled?              —       —      —
  6. Deployment risk manageable?       —       —      —
CONFIRMED = native + outside agree; primary cannot replace outside. DISAGREE → taste.
Missing/disabled voice = N/A, never CONFIRMED. Flag any single-voice critical finding.
```

3. Section 1 (Architecture): Produce ASCII dependency graph showing new components
   and their relationships to existing ones. Evaluate coupling, scaling, security.

4. Section 2 (Code Quality): Identify DRY violations, naming issues, complexity.
   Reference specific files and patterns. Auto-decide each finding.

5. **Section 3 (Test Review) — NEVER SKIP OR COMPRESS.**
   This section requires reading actual code, not summarizing from memory.
   - Read the diff or the plan's affected files
   - Build the test diagram: list every NEW UX flow, data flow, codepath, and branch
   - For EACH item in the diagram: what type of test covers it? Does one exist? Gaps?
   - For LLM/prompt changes: which eval suites must run?
   - Auto-deciding test gaps means: identify the gap → decide whether to add a test
     or defer (with rationale and principle) → log the decision. It does NOT mean
     skipping the analysis.
   - Write the test plan artifact to disk

6. Section 4 (Performance): Evaluate N+1 queries, memory, caching, slow paths.

**Mandatory outputs from Phase 3:**
- "NOT in scope" section
- "What already exists" section
- Architecture ASCII diagram (Section 1)
- Test diagram mapping codepaths to coverage (Section 3)
- Test plan artifact written to disk (Section 3)
- Failure modes registry with critical gap flags
- Completion Summary (the full summary from the Eng skill)
- TODOS.md updates (collected from all phases)

**Close this phase:**

The review work above ends here. Now load the shared close steps afresh, even if
read earlier. Use phase `eng`, checkpoint `<ENG_INPUT>`, and this phase's
methodology files. Keep this checkpoint for this invocation; review exports do not replace it.

> **STOP.** Read `references/phase-close.md` afresh and execute it
> in full. Do not work from memory — that section is the source of truth for this step.
