---
type: engineering-requirements
spec: ./spec.md
spec_sha256: 5041109e3d7052515e1ec5cc6858451c91b5abca9705d94a9b911886cadc4a02
reviewer: bench
seated: [boris, eng-failure, eng-observability, eng-test, eng-authz, eng-rollback, eng-release]
reviewed_at: 2026-11-12T16:14:40+1000
status: PASS
categories:
  data_model:         {state: N/A, reason: "The line only reads the HARD_STOP marker and the hook payload on stdin; it creates no row, file or table and nothing is owned or cascades.", by: boris}
  invariants:         {state: DECIDED, ref: "#invariants", by: eng-authz}
  failure_modes:      {state: DECIDED, ref: "#failure-modes", by: eng-failure}
  interface_contract: {state: DECIDED, ref: "#interface-contract", by: boris}
  concurrency:        {state: N/A, reason: "No queue, worker, lock, shared file or second writer: the line writes nothing and reads only the HARD_STOP marker and stdin.", by: boris}
  migration:          {state: N/A, reason: "No *.sql file, schema file or supabase/migrations entry is in this diff; only .claude/settings.json and two test files change. The standing ledger drift is untouched.", by: eng-release}
  rollback:           {state: PRESCRIBED, ref: "#rollback", by: eng-rollback}
  observability:      {state: DECIDED, ref: "#observability", by: eng-observability}
  budget:             {state: N/A, reason: "Each tool call still starts one shell and one python3, as today; the extra file tests cost microseconds and nothing spends or grows.", by: boris}
  test_oracle:        {state: DECIDED, ref: "#test-oracle", by: eng-test}
disagreements:
  - "boris filed the stale home copy under migration; eng-release filed migration N/A and the stale copy under failure_modes. Chair ruling (lead): the stale copy is a failure mode of the home fallback, and amendment 1 removes the fallback, so migration is N/A and the copy is closed under failure_modes; the stale clone itself is a follow-up card."
  - "boris and eng-release asked for a rollout step that repoints ~/.claude/hooks/autonomy_gate_hook.py and pulls stale checkouts. Ruled out of this change: user-level hook configuration on a machine is out of scope (spec section 5) and hook changes are a founder-floor action. Recorded as a follow-up with an owner instead."
---

# Engineering requirements: RA-8340

Seven seats ran cold and read-only. Every blocking finding was answered by amendment 1 of the spec, so no category
blocks. What the bench found that the first draft did not contain, by seat:

- eng-release and eng-authz: the home fallback ran a stale pre-RA-8125 copy that cannot import. Fallback removed.
- eng-failure, eng-test, eng-authz, boris: a failed gate's partial stdout plus the deny is not one JSON document,
  so the HARD_STOP deny would be ignored. Output now captured; on failure only the deny prints.
- eng-observability: stderr on exit 0 never reaches the model. The off note is now additionalContext.
- eng-test: the RA-8125 test accepted any deny, so it no longer guarded the import. It now rejects the fallback deny.
- eng-rollback: a shell syntax error exits 2 and bricks the session that saves the file. The patch step now
  refuses a line that `bash -n` or `sh -n` rejects, and the tests run under both shells.

Round 2 (spec amendment 2, after Codex round 1 on 602b9e94): the kill switch no longer depends on the gate at
all. The line checks HARD_STOP first and prints only the deny, which closes both the bench's two-document finding
and Codex's silent-allow finding as one kind. The notice JSON is built by `json.dumps`, closing the quoted-path
finding. Invariants, failure modes and the test oracle below are unchanged in intent; the tests now cover every
gate behaviour under HARD_STOP and a quoted path.

Round 3 (spec amendment 3, after Codex round 2 on 686aefe5): with no python3 the notice encoder failed too, so the
session was told nothing. Second finding of the kind "stdout JSON produced by a step that can fail"; the design
now ends every stdout path in a constant that needs only shell builtins, with python3 as optional enrichment.

Round 4 (spec amendment 4, after Codex round 3 on 69ab8cda): a garbage-printing python3 corrupted the enriched
notice, the third finding of kind B, so the enrichment is gone: the line writes only constants to stdout, and the
expanded path and exit code go to stderr. This narrows eng-observability's notice to "which case happened"; the
detail stays on stderr. Successful gate output passes through unchecked as at base: a named limit, checked
against the owner by a real-gate test. HARD_STOP is now read via `~`, matching the gate when HOME is unset.

Round 5 (spec amendment 5, after Codex rounds 4 and 5): kind C, "a stated guarantee with no test that can fail on it", reached three instances. Every guarantee is now in one claims ledger in the spec with a killed mutant (12 of 12, run in a throwaway worktree); two were narrowed to named limits (NUL bytes, unset HOME under dash). The tests run under dash too, which is `/bin/sh` on GitHub's runners.

## Invariants

> reaches the model; when HARD_STOP is set, every tool call is still refused, script or no script.

By eng-authz. The guarantees, their tests and their killed mutants are listed once, in the claims ledger of spec
amendment 5 (G1 to G12, limits L1 to L3); this section points there and restates none of them. I1 is G2: while
HARD_STOP exists, every call is denied whatever the gate does. I3, the L3 deny is off, holds in two cases, never
silently: no project copy exists (G1, G10), or the gate exits non-zero, including a crash after import (G5). In both
cases the session gets the constant notice. The tests run under bash, sh and dash.

## Failure modes

> 2. If `f` exists: run it with its stdout captured. Exit 0 passes the captured output through and stops.

By eng-failure, with eng-release. A gate that prints and then fails no longer leaks its text in front of the deny.
A crashing gate without HARD_STOP gets the same constant notice as a missing one (G5); its path and exit code go to
the hook's stderr only. The home fallback is
gone, so the stale clone at `/Users/phill-mac/Pi-Dev-Ops` cannot be selected by this line. Residual, accepted and
written down: "off" fails open for L3 with no counter or alert outside the session (owner RA-8126).

## Interface contract

> 5. Otherwise print the additionalContext JSON with the recorded reason, exit 0. Never exit 2.

By boris. Claude Code reads hook stdout as JSON only when it is one object with nothing but whitespace around it.
The wrapper prints either the gate's own successful output, one deny object, or one additionalContext object, and
always exits 0 after the gate decision. The deny and note texts contain no apostrophe or backslash, so they survive
single quoting; the wrapper prints them with `printf '%s\n'`, never `echo`, and relays a successful gate's output with `printf '%s'` after a sentinel capture, so only NUL bytes are lost.

## Rollback

By eng-rollback. Nothing here is irreversible. Sequence at 3am: (1) a gate letting an L3 call through: `touch
~/.claude/HARD_STOP`, which denies every call with or without the script; (2) blocking when it should allow: only
possible under HARD_STOP, so `rm ~/.claude/HARD_STOP` from a terminal outside Claude Code; (3) only then `git revert`
the merge and pull every checkout, knowing the revert restores the RA-8340 outage. A hand edit that breaks the
quoting exits 2 and blocks the editing session; recover with `git -C <checkout> checkout origin/main --
.claude/settings.json` from a terminal.

## Observability

> cannot be found or fails, the session keeps working and is told so through PreToolUse `additionalContext`, which

By eng-observability. The off notice reaches the model through PreToolUse additionalContext as constant text: it
says which case happened (no copy, or the gate failed), names the path only as the literal
`$CLAUDE_PROJECT_DIR/.claude/hooks/autonomy_gate_hook.py`, and cites RA-8340. The expanded path and the exit code
go to the hook's stderr, which the model does not see (spec amendment 4, the trade recorded against this seat). Merged is not in effect: each checkout carries its own settings, so
"in effect" is observed after merge per checkout (spec section 15), reported separately, owner the lead chat.

## Test oracle

> Each test runs the actual registered command through `/bin/bash -c` and `/bin/sh -c`. Cases: nothing installed

By eng-test. `tests/test_hook_missing_script_never_blocks.py` runs the real registered command under `/bin/bash` and
`/bin/sh` with `GIT_CEILING_DIRECTORIES` set, parses the whole of stdout as JSON for every deny and note, and runs
the class guard over every registration (floor of 8 so an empty parse cannot pass). Watched red on origin/main's line
(11 failed, 6 passed: the passing ones are behaviour the old line already had) and green after (17 passed with C2).
The strengthened RA-8125 assertion was watched red by restoring the `abspath` line in a copy-and-restore run.
