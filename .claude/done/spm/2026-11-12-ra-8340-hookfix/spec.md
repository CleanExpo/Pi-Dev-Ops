# Spec: RA-8340, the autonomy gate hook must never block every tool when its script is missing

> Amendment 5 (12/11/2026, after Codex rounds 4 and 5 on 2491cf2e and a5c2350e). It wins over amendments 4 to 1.
> - Kind C, "a stated guarantee with no test that can fail on it", seen three times: the bench (the RA-8125 test
>   accepted any deny), round 4 (the unset-HOME test always set HOME), round 5 (the relay promised unchanged bytes
>   and `$(...)` dropped trailing newlines). Design change: every guarantee below is listed with the test that
>   guards it and a mutant run, made in a throwaway worktree, that the test kills. A guarantee with no killed
>   mutant is either narrowed to what was proven or named as a limit. No guarantee is stated anywhere else.
> - Wording fix to amendment 4: the line authors only constants on stdout; on gate exit 0 it relays the gate's
>   output. The relay keeps every byte (sentinel capture, `printf '%s'`) except NUL bytes.
> - Claims ledger. Mutants by `mutants_all.py` at 8bb3e175, all 12 KILLED, files restored byte-identical:
>   - G1 no registration exits 2 when nothing is installed (base registration planted: 6 failed)
>   - G2 HARD_STOP present: stdout is only the deny, whatever the gate does (check disabled: 37 failed)
>   - G3 HOME unset, under bash: the line tests the same HARD_STOP path as the gate (`$HOME` planted: 1 failed)
>   - G4 gate exit 0: its output is relayed unchanged apart from NUL bytes (round-4 capture planted: 15 failed)
>   - G5 gate exits non-zero: its own output is dropped, one notice is printed (output leaked: 3 failed)
>   - G6 the gate receives the payload on stdin (stdin from /dev/null: 1 failed)
>   - G7 the home copy is never run (home path planted: 1 failed)
>   - G8 the notice is valid JSON for any folder name (path interpolated into it: 3 failed)
>   - G9 python3 cannot change what the line prints (python3 call planted before the notice: 3 failed)
>   - G10 with no python3 the session is still told the gate is off (127 treated as success: 3 failed)
>   - G11 the real gate prints nothing or one JSON object (stray print in the gate: 6 failed)
>   - G12 RA-8125: the settings line runs the trusted gate (abspath restored: 1 failed)
> - Named limits, each pinned or stated, not claimed:
>   - L1 NUL bytes in a successful gate's output are dropped: a shell variable cannot hold one. Pinned by
>     `test_named_limit_a_nul_byte_in_gate_output_is_dropped`. The real gate writes `json.dumps` output.
>   - L2 HOME unset under dash: dash leaves a bare `~` unexpanded, so neither `~` nor `$HOME` finds the marker.
>     G3 is bash-only. Claude Code always sets HOME for hooks.
>   - L3 on gate exit 0 the content is not validated, as before RA-8340; the gate owns it (G11 checks the owner).
> - The tests now run under `/bin/dash` too wherever it is installed, because `/bin/sh` is dash on GitHub's
>   Ubuntu runners and bash on macOS.

> Amendment 4 (12/11/2026, after Codex review round 3 on 69ab8cda: one P1, all eight checklist items PASS). It
> wins over amendments 3, 2 and 1.
> - Round 3 was the third finding of kind B, "stdout JSON produced by a step that can fail or corrupt it"
>   (printf interpolation; a missing encoder; an encoder that prints garbage). The rule changes, not the
>   fallback: the line writes ONLY shell constants to stdout. No encoder and no interpolation. The notice names
>   the path as the literal text `$CLAUDE_PROJECT_DIR/.claude/hooks/autonomy_gate_hook.py`; the expanded path
>   and the exit code go to the hook's stderr. Trade, recorded against eng-observability: the model no longer
>   sees the expanded path or exit code, only which of the two cases happened.
> - Every stdout path and who writes its bytes:
>   - HARD_STOP present: a constant deny (the line). The gate is not run.
>   - gate exits 0 with output: the gate's own bytes, unchanged, exactly as before RA-8340.
>   - gate exits 0 silently: nothing, which is the PreToolUse "no decision" answer and the real gate's normal
>     allow for L0 to L2 calls (`decide()` returns None).
>   - gate exits non-zero: a constant "ran but failed" notice (the line).
>   - gate missing: a constant "no copy" notice (the line).
> - Named limit (house rule step 4): when the gate exits 0, the line passes its stdout through unchecked, as the
>   original registration did. The gate owns that output. A test now checks the owner: the real gate, fed
>   empty, unparseable, non-object and L0/L3 input, prints nothing or exactly one JSON object.
> - Kind A edge found while enumerating: with HOME unset, `$HOME/.claude/HARD_STOP` is `/.claude/HARD_STOP` while
>   the gate's `expanduser` reads the passwd home. The line now reads `~/.claude/HARD_STOP`, which bash and sh
>   resolve to the passwd home when HOME is unset (probe output: `~` gives /Users/phill-mac, the same path as
>   `os.path.expanduser`). A test covers a HOME containing a space.

> Amendment 3 (12/11/2026, after Codex review round 2 on 686aefe5: one P1, all eight checklist items PASS). It
> wins over amendments 2 and 1.
> - Finding: with no `python3` on PATH the gate cannot run and the round-2 notice encoder (also `python3`) could
>   not either, so the session got nothing while L3 calls went ungated.
> - Kind: this is the second finding of one kind, "stdout JSON is produced by a step that can fail or corrupt
>   it" (round 1: `printf` interpolation; round 2: a missing encoder). Design change for the kind: every stdout
>   path of the line now ends in output that needs only shell builtins (`[`, `printf`, assignment). The HARD_STOP
>   deny was already a constant. The notice is captured from the encoder, and if the encoder fails or prints
>   nothing, a constant JSON notice is printed instead. `python3` only adds the path and exit code.
> - Tests: no `python3` on PATH, gate missing or present, under bash and sh, gives one valid additionalContext
>   JSON; HARD_STOP with no `python3` still denies.

> Amendment 2 (12/11/2026, after Codex review round 1 on 602b9e94, which returned two P1 findings). It wins
> over amendment 1 and every section below where they differ.
> - Kill switch: the settings line checks `~/.claude/HARD_STOP` FIRST and, when it exists, prints only the deny
>   and exits 0 without running the gate. Reason: the real gate returns 0 with no output on input it cannot
>   parse, before it reads HARD_STOP, so a line that trusts a successful gate let calls through under HARD_STOP.
>   The bench's earlier finding (gate output plus an appended deny is not one JSON document) is the same kind:
>   the kill switch depended on what the gate printed or returned. The line is now the single owner of the
>   HARD_STOP check; the gate keeps its own check for callers that reach it directly.
> - Notice text: the additionalContext JSON is built by Python's `json.dumps`, with the path and exit code passed
>   as an argument, never pasted into JSON text by `printf`. Reason: a `"` in the project folder name made the
>   notice invalid JSON.
> - Tests: one parametrized HARD_STOP test over every gate behaviour (missing, silent allow, prints then allows,
>   crashes, the real gate) with valid and unparseable input, under bash and sh; one test with a quote, a
>   backslash and a tab in the project path. The RA-8125 settings test now runs without HARD_STOP and sends an L3
>   call that only the real gate denies, so it still fails when the real gate cannot import.
> - Still one changed line in `.claude/settings.json`; `autonomy_gate_hook.py` unchanged.

> Amendment 1 (12/11/2026, after the engineering bench): home-folder fallback removed (the Mini's home copy is
> a stale pre-RA-8125 file that cannot import: eng-release, eng-authz); the gate's stdout is captured so a
> failed run prints only the deny (eng-failure, eng-test, eng-authz); the "off" note moves from stderr to
> PreToolUse additionalContext and also covers a crashing gate (eng-observability, eng-authz); the patch step
> refuses a line that `bash -n` or `sh -n` rejects (eng-rollback); tests run under bash and sh with
> GIT_CEILING_DIRECTORIES set (eng-test); the RA-8125 test must reject the fallback deny (eng-test).

Lane: full spec. Tier T3 (`tier.py 0 1 0 1 2`: F0 two files; I1 hook config with rollback; N0 the RA-8127
pattern already in this file; X1 security plus ops; S2 the change decides when a permission gate applies).
Release review: Tier 1 (a permissions control). Human merge only.

## 1. Task

Board card `1PCT-PDO-AUTONOMY-HOOK-MISSING-FILE-BRICKS-SESSION`, assigned by the lead chat on 12/11/2026:
guard the `.claude/settings.json` registration that runs `autonomy_gate_hook.py`, the way RA-8127 guarded the
senior-harness and continuation-horizon registrations, so a missing script is reported and never exits 2, while a
present script still runs and denies. Check every hook registration for the same pattern and fix the class. Test
that fails on the old registration. Pull request for Phill to merge.

## 2. Current context

- Grounded 12/11/2026: `.claude/settings.json:94` on origin/main `1b2bcd96` is
  `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/autonomy_gate_hook.py"`, registered on PreToolUse with matcher `*`.
  Source: `git show origin/main:.claude/settings.json`.
- Grounded: `python3 <missing file>` exits 2. For PreToolUse, exit 2 is "block this tool call". Source: the
  scratch red run below, and Claude Code hook semantics.
- Grounded: on 12/11/2026 the Package C chat's project folder was not the repository; every tool call was
  refused for over an hour (board card note).
- Grounded: `autonomy_gate_hook.py` (RA-6874) denies L3 calls and every call while `~/.claude/HARD_STOP` exists,
  always through JSON on stdout with exit 0. RA-8125 made its import work through a symlink.
- Grounded: `~/.claude/hooks/autonomy_gate_hook.py` on the Mini is a symlink into `/Users/phill-mac/Pi-Dev-Ops`,
  a checkout on `feature/spm-software-factory` whose hook still uses `abspath` (line 15), the pre-RA-8125 form
  that cannot import through a symlink (eng-release, eng-authz, both by Read). It is not a usable fallback.
- Grounded: the user-level `~/.claude/settings.json` on the Mini registers no autonomy-gate hook, so sessions get
  it only from a project-level `.claude/settings.json` (eng-release, by Read).
- Done gate: `donectl selftest` ran in this worktree; spec-work contract `w_1321969b276c` was locked, then went
  STALE when this spec was written; it is revised and relocked after this amendment.

## 3. Problem and value

A wrong project folder turns a safety gate into a total outage: the session cannot run the command that would
move it. The cost on 12/11 was over an hour of a lead-assigned chat. RA-8127's answer ("missing means off,
silently") is wrong for this hook alone: it would also switch off the HARD_STOP kill switch, the one control
meant to stop every agent at once. Revenue lens: none directly; it protects the fleet's uptime and the kill switch.

## 4. Desired outcome

Any session, in any folder, can always run tools unless a real gate decides otherwise. When the gate script
cannot be found or fails, the session keeps working and is told so through PreToolUse `additionalContext`, which
reaches the model; when HARD_STOP is set, every tool call is still refused, script or no script.

## 5. Scope

In: the one registration at `.claude/settings.json:94`; one new test file with a class guard over every
registration; one added assertion in `tests/test_autonomy_gate_hook_paths.py` (eng-test).
Out: packaging hooks as a plugin so they stop depending on `$CLAUDE_PROJECT_DIR` (RA-8126); changing
`autonomy_gate_hook.py` or `swarm/nexus/autonomy_gate.py`; the user-level settings on any machine.

## 6. Existing capability

Searched: `git grep -n autonomy_gate_hook`, `tests/test_hook_missing_target_quiet.py` (RA-8127 guard),
`tests/test_autonomy_gate_hook_paths.py` (RA-8125, expects a deny from the settings command and must stay green),
Linear search "autonomy_gate_hook" (RA-8125, RA-8126, RA-6874). The guard pattern exists; the HARD_STOP-aware
variant does not.

## 7. Specialist bench receipt

Engineering bench via `engineering-requirements` (see `engineering.md`). Seats: boris, eng-failure,
eng-observability, eng-test (core), eng-authz (the change decides when a permission gate applies),
eng-rollback (hook config affects every session).

## 8. Judge challenge

Score 92/100, APPROVE EXPERIMENT until the release review passes. Deductions, as amended after the bench:
- (-4, closed by amendment 1) The home fallback ran a stale copy. It is removed.
- (-4, reduced) The "off" note now reaches the model through additionalContext, but nothing counts or alerts on
  it outside the session, and it repeats on every call. Owner: RA-8126 (the permanent design).
- (open) Merged is not in effect: each checkout and worktree carries its own `.claude/settings.json`, so a merge
  fixes a session only after its checkout pulls main. Owner: the lead chat, named on the board card; listed as
  a follow-up in the PR body with the checkouts known to hold the old line.
Hard-day case: HARD_STOP set during an incident while sessions run from odd folders. Today those sessions are
already blocked (by accident); after the change they are still blocked, on purpose, with a reason that names
HARD_STOP.

## 9. Proposed solution

Replace the registration with one shell line (no home fallback):
1. `f` = `$CLAUDE_PROJECT_DIR/.claude/hooks/autonomy_gate_hook.py`.
2. If `f` exists: run it with its stdout captured. Exit 0 passes the captured output through and stops.
   Any other exit records "`$f` exited `<rc>`" and drops the captured output.
3. If `f` is missing: record "no copy at `$f`".
4. HARD_STOP present: print only the deny JSON, exit 0.
5. Otherwise print the additionalContext JSON with the recorded reason, exit 0. Never exit 2.

## 10. UX requirements

The deny reason names HARD_STOP, says the gate script was not found or failed, and says how to clear it
(remove `~/.claude/HARD_STOP`). The "off" note names the missing path, or the path and exit code, and RA-8340.

## 11. Technical requirements

- Exactly one registration changes; every other byte of `.claude/settings.json` is unchanged.
- The command uses only POSIX shell plus `python3`, like the RA-8127 commands.
- No registration in the file may exit 2 when nothing is installed and the project folder is not the repo.

## 12. Security and privacy

The kill switch fails closed: HARD_STOP denies even with no script and even when the script crashes, and the
deny is then the only thing on stdout, so Claude Code parses it. The L3 deny is off when no importable project
copy exists. This is a loosening against today, where such a session is blocked entirely, L3 included; it is
the accepted residual, it is told to the session through additionalContext, and RA-8126 removes it. Known
limit, unchanged by this change: the HARD_STOP path is written in the shell line, in `autonomy_gate_hook.py:23`
and as `TAO_HARD_STOP_FILE`'s default; only the last honours an override. No secrets, no network, no new inputs.

## 13. Verification plan

Guard tests in `tests/test_hook_missing_script_never_blocks.py`, run against the real `.claude/settings.json`
with a temporary HOME and a project folder that is not the repo. Each is watched failing on origin/main's
registration before the change. Container strategy: the tests run hook commands in a subprocess with a clean
environment (`HOME`, `CLAUDE_PROJECT_DIR`, `PATH=/usr/bin:/bin`, `GIT_CEILING_DIRECTORIES` at the temp folder)
inside pytest's temporary folder; nothing touches the real HOME, HARD_STOP or any outer repository.
`tests/test_autonomy_gate_hook_paths.py` additionally asserts its deny reason does not carry the fallback's
RA-8340 marker, so the RA-8125 regression still fails when the real gate cannot import.

## 14. Loop and stress testing

Each test runs the actual registered command through `/bin/bash -c` and `/bin/sh -c`. Cases: nothing installed
(every registration), missing gate without HARD_STOP (additionalContext), missing gate with HARD_STOP (one JSON
deny), project copy output passed through, home copy never run, crashing gate without HARD_STOP
(additionalContext naming path and exit code), crashing gate that printed first under HARD_STOP (stdout is only
the deny). Plus the existing `test_autonomy_gate_hook_paths.py` and `test_hook_missing_target_quiet.py` stay green.

## 15. Acceptance criteria (become the Done contract)

- C1 `.venv/bin/python -m pytest -q tests/test_hook_missing_script_never_blocks.py`
- C2 `.venv/bin/python -m pytest -q tests/test_autonomy_gate_hook_paths.py tests/test_hook_missing_target_quiet.py`
- C3 `python3 -c "import json;json.load(open('.claude/settings.json'))"` (valid JSON)
- C4 `test "$(git diff --numstat 1b2bcd96 -- .claude/settings.json)" = "$(printf '1\t1\t.claude/settings.json')"`
  (exactly one line of `.claude/settings.json` changes)
- C5 `bash scripts/handoff-loop.sh` reads READY

Not a Done criterion, because it can only be observed after Phill merges: "in effect". After merge, each checkout
a session can load (`git worktree list`, plus `/Users/phill-mac/Pi-Dev-Ops`) reads `grep -c RA-8340
.claude/settings.json` ≥ 1, and one fresh session in a non-repo folder runs a Read without refusal. Reported
separately from "merged"; owner the lead chat.

## 16. Goal command

`/goal` build RA-8340 to the locked criteria C1 to C5, then independent Tier 1 review, release gate, draft PR.

## 17. Implementation sequence and crew

1. Copy the drafted test into `tests/`; run it red on the current registration.
2. Apply the one-line registration change; run green; run C2.
3. Lock the build contract; local gates; independent review (Codex, then Cursor); release gate; draft PR.
Crew: lead (Opus) builds; bench seats read-only; reviewer from another vendor.
Loadout: spm (front door), engineering-requirements (bench), done-harness (contract), pr-release-gate (release).

## 18. Session-handoff seed

Branch `fix/RA-8340-autonomy-gate-missing-script` in `.claude/worktrees/ra-8340-hookfix`. First command:
`.venv/bin/python -m pytest -q tests/test_hook_missing_script_never_blocks.py`.

## 19. Recommendation

Build it. One line of config, fails closed on the kill switch, and a class guard that stops the next
unguarded registration from repeating the outage.
