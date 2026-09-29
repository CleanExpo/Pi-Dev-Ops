# Eval-first discipline (§D — "start with evaluation")

The eval is written in phase 4, BEFORE any skill body exists, and is the definition of
done. A skill without a passing eval is not a skill; it is a draft.

## eval.md format (lives in the skill's dir)

```markdown
# eval — <skill-name>
## Checks (all must pass, fresh, same turn as any "done" claim)
1. <claim being proven> → `<exact command>` → expect: <observable result>
2. …(3–7 checks)
N. NEGATIVE: <input the skill must refuse/flag> → `<command>` → expect: refusal/flag
```

## Rules

- **Red first.** Run the eval immediately after writing it; every check must FAIL
  (or error) before implementation. An eval that passes against nothing is testing nothing.
- **Executable, not vibes.** Each check is a command with an observable expectation —
  exit code, output substring, file existence, count. No "looks correct".
- **One negative case minimum.** The skill must demonstrably refuse or flag its
  designed failure input (planted secret, out-of-scope target, uncited claim…).
- **Fresh at claim time (§C).** Phase 7 reruns the whole eval in the same turn as the
  completion claim, stamped through `evidence.py` (run-ID + UTC + sha256). Cached green
  is not green.
- **Variance analysis.** If a check involves model output, run it 3×; if results
  disagree, the check is under-specified — tighten the expectation or make the step
  deterministic (code, not model), then rerun.
- **No reward hacking.** The skill never edits its own eval to pass, and never fetches
  the expected answer from the eval file. Either is an automatic phase-7 FAIL and gets
  flagged in the AI-BOM.
