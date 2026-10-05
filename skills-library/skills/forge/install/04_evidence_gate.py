#!/usr/bin/env python3
"""04_evidence_gate.py — groundtruth-pattern fresh-evidence gate (§C, ASI09).

Blocks turn-end ONLY when the final assistant message makes a strong completion
claim AND the turn contains zero tool activity (a pure-narrative "done"). Every
verified claim in this estate must trace to a same-turn tool result; a done-claim
with no tool use at all cannot have one.

Deliberately conservative — the sibling 03_quality_gate.py owns nuanced review;
this gate catches only the indefensible case, so false positives stay near zero.
Escape hatches: unparseable transcript (fail open, and announced), explicit
retraction language, or stop_hook_active (never double-fire in one stop cycle).
There is deliberately NO environment-variable switch: see main().
Exit contract (Claude Code Stop hook): JSON {"decision":"block","reason":...} on
stdout to block; empty output to allow.
"""
import json, os, re, sys

# The reporter must never take the hook down with it: if hook_failure.py is
# missing, fall back to stderr rather than raising. install.py proves the real
# import works, so this fallback should never be the live path.
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from hook_failure import record_failure, record_skip
except Exception:  # noqa: BLE001
    # Guarded for the same reason as the real module's last-resort write: these
    # reporters are called BEFORE the fail-open systemMessage is printed, so a closed
    # or broken stderr here would kill the hook before the operator learns the gate
    # did not run. Found by independent review 2026-08-29.
    # Formatting happens INSIDE the guard. An f-string built at the call site is
    # evaluated before the guarded function is entered, so an argument whose __repr__
    # or __str__ raises would escape — the same hole the real module had one layer
    # down. Found by independent review 2026-08-29.
    def _shim(*parts):
        try:
            sys.stderr.write(" ".join(str(p) for p in parts) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def record_failure(hook, where, exc=None, note=None):
        _shim("[hook-failure:no-module]", hook, where, exc, note)

    def record_skip(hook, reason):
        _shim("[hook-skip:no-module]", hook, reason)

CLAIM = re.compile(
    r"\b(all tests pass|tests? (are )?passing|build (succeeds|passes|is green)|"
    r"deployed successfully|everything works|fully (working|implemented|verified)|"
    r"task( is)? complete[d]?|done and verified|verified and (working|complete)|"
    r"gates? (are )?green|confirmed working)\b",
    re.I,
)
RETRACTION = re.compile(r"\b(retract|cannot verify|unverified|not (yet )?verified|have not (run|tested))\b", re.I)

def main():
    # A SKIP_EVIDENCE_GATE=1 escape hatch used to sit here and it was removed.
    # An environment variable proves nothing about WHO set it: any process,
    # script or agent inside this session could set it, and this one returned
    # silently, so a disabled gate was byte-identical to a clean pass. That is a
    # bypass wearing the word override. The honest way past this gate is to run
    # the command that proves the claim, or to retract the claim -- both of which
    # the block message already spells out. Same defect class as the
    # ESTATE_SYNC_VISIBILITY_GUARD and STANDARDS_EGRESS_OVERRIDE bypasses.
    # Filed P1 by independent review 2026-08-29.
    try:
        # stdin decodes with the locale codec (cp1252 on Windows) unless told
        # otherwise. A payload with one curly quote used to land in the fail-open
        # handler below, so the gate returned silently and read as a pass.
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        payload = json.load(sys.stdin)
    except Exception as e:
        record_failure("04_evidence_gate", "read-stdin", e)
        # Same rule as the transcript-scan handler below: the turn proceeds, but the
        # operator is TOLD the gate did not run. Recording to the hook-failure log is
        # not enough — the agent never reads that file, so a silent return still looks
        # exactly like a clean pass. This was the SECOND fail-open path; only the
        # transcript one was announced. Found by independent review 2026-08-29.
        print(json.dumps({
            "systemMessage": (
                "Evidence gate (04) DID NOT RUN: the hook payload could not be read "
                f"({type(e).__name__}). Completion claims this turn are UNVERIFIED by "
                "this gate."
            )
        }))
        return  # fail open, but not silently
    if payload.get("stop_hook_active"):
        return
    # Stop supplies the current reply before it is guaranteed to reach the transcript.
    # A transcript tail can be an older reply or intermediate commentary, so the payload's
    # copy wins. A payload without one (an older Claude Code, the installer's probe)
    # falls back to the transcript's last text block, as this gate always did.
    final_text = payload.get("last_assistant_message")
    use_payload_text = isinstance(final_text, str)
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        # The THIRD fail-open path, and the last silent one. Same rule as the two
        # handlers around it: no transcript means the turn cannot be scanned, so the
        # gate did not run — and a check that could not run must never look like a
        # check that passed. This one was easy to miss because it reads as ordinary
        # input validation rather than as error handling. Found 2026-08-29 by a
        # control that fed the gate a nonexistent transcript_path and got silence
        # back, indistinguishable from a clean pass.
        reason = "transcript_path absent from payload" if not path else "transcript file does not exist"
        record_skip("04_evidence_gate", reason)
        print(json.dumps({
            "systemMessage": (
                f"Evidence gate (04) DID NOT RUN: {reason}. Completion claims this "
                "turn are UNVERIFIED by this gate."
            )
        }))
        return  # fail open, but not silently
    try:
        turn = []  # entries after the last real user message
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("type") == "user" and not e.get("isMeta"):
                    # tool_result entries also arrive as type=user; keep those in-turn
                    content = e.get("message", {}).get("content")
                    is_tool_result = isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("type") == "tool_result" for c in content
                    )
                    if not is_tool_result:
                        turn = []
                        continue
                turn.append(e)
        tool_activity = 0
        if not use_payload_text:
            final_text = ""
        for e in turn:
            if e.get("type") != "assistant":
                continue
            for c in e.get("message", {}).get("content", []) or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tool_activity += 1
                if not use_payload_text and isinstance(c, dict) and c.get("type") == "text":
                    final_text = c.get("text", "")
        if not final_text or tool_activity > 0:
            return
        if CLAIM.search(final_text) and not RETRACTION.search(final_text):
            print(json.dumps({
                "decision": "block",
                "reason": ("Evidence gate (04): the reply claims completion/verification but this turn "
                           "ran zero tools, so no fresh same-turn evidence can exist. Either run the "
                           "command that proves the claim now and attach its output, or retract the "
                           "claim explicitly (e.g. 'unverified')."),
            }))
    except Exception as e:
        record_failure("04_evidence_gate", "scan-transcript", e)
        # Fail OPEN, but never SILENT. A Stop hook that fails closed on an unreadable
        # transcript cannot be satisfied by any assistant action, so it livelocks the
        # session — the failure goal-circuit-breaker exists for. The turn proceeds, but
        # the operator is TOLD the gate did not run: a check that could not run must
        # never look like a check that passed. Found by independent review 2026-08-29.
        print(json.dumps({
            "systemMessage": (
                "Evidence gate (04) DID NOT RUN: the transcript could not be scanned "
                f"({type(e).__name__}). Completion claims this turn are UNVERIFIED by "
                "this gate."
            )
        }))
        return

if __name__ == "__main__":
    main()
