---
name: control-readout
description: Use when about to INTERPRET the result of a check you did not write — a CI conclusion, a test verdict, a gate outcome, a health payload, a query returning zero rows — and above all when about to dismiss a failure as pre-existing, environmental, flaky, unrelated or "already broken". Triggers on "already failing", "pre-existing", "same before and after", "not caused by my change", "just the environment", "skipped", "no results", "looks clean", "it was already red".
allowed-tools: Read, Grep, Glob, Bash
---

# Control Readout — reading a verdict you did not write

`control-design` owns the **write** path: designing a check so it can fail. This skill owns
the **read** path: interpreting a check's output without inheriting its blind spots. Both
halves are needed. Every defect in the 2026-08-03 Pi-Dev-Ops session was found on the read
path, and the one mistake that survived to a PR body was a misread, not a mis-design.

The governing asymmetry: **a control's silence has two causes — nothing was wrong, or nothing
was checked — and they render identically.** Every rule below is a way of telling them apart.

## The four rules

### 1. A differential ATTRIBUTES. It does not EXONERATE.

Running a check at base and at your candidate and getting the same result answers exactly one
question: *did I cause it?* It does not answer *is it broken?* Those are independent, and a
differential can only ever settle the first.

The trap is that "identical before and after" **feels** like a clean bill of health, because
it is the same evidence you use to clear yourself. It is not. Answer both questions out loud:

```
Did my change cause it?   -> differential (base vs candidate)
Is it actually a defect?  -> read the error, on its own terms
```

**Completion criterion:** for every failure you are about to set aside, you have written both
answers, not one. If the second is "unknown", it is not set aside.

### 2. Prove the control RAN before you read its verdict.

`skipped` is not `passed`. `not run` is not `clean`. A job conclusion is an aggregate and it
lies by omission: read the **step list**, not the summary.

```bash
# WRONG — the conclusion tells you a job failed, not which controls executed
gh run view <id> --json conclusion

# RIGHT — which steps actually ran, and which never got the chance
gh run view <id> --json jobs --jq '.jobs[] | .steps[] | "\(.name): \(.conclusion)"'
```

**Completion criterion:** for every control you are citing as evidence, you have seen it
report a result — not merely seen the surrounding job go green or red.

### 3. A red baseline hides other red.

"It was already failing" is the single most dangerous sentence on the read path, because it is
usually true and it terminates the investigation. The baseline being red is not a reason to
skip reading *what* is failing — **the reason can change underneath you**, and a cheap early
failure will mask expensive later ones indefinitely.

Ordering is the mechanism: any runner stops a job at the first failing step, so a lint error
standing in front of a test suite deletes the test suite's signal entirely, and the job still
reports one honest-looking red.

**Completion criterion:** you have read the actual failing message at the baseline, not just
its red/green. If the baseline's failure reason differs from the candidate's, they are two
findings, not one.

### 4. Absent is not benign — it is UNKNOWN.

A control that has never executed has *unknown* state. Not good state. The instinct to read
"no findings" or "no history" as reassurance is exactly backwards: it is the least informative
possible output, and it is what a completely broken control produces.

Corollary, and expect it: **fixing a masking failure surfaces more failures.** That is the fix
working, not a regression you introduced. Say so plainly when reporting, or the improvement
reads as damage and gets reverted.

**Completion criterion:** you have classified each quiet control as *verified clean* or
*never ran*, and never merged the two into "fine".

## The readout checklist

Before any sentence containing "pre-existing", "environmental", "unrelated" or "already
broken":

1. Did this control **execute**? (step list, not job conclusion)
2. If it failed at base too — what is the **actual message** at base? Same message, or just
   same colour?
3. Am I using a differential to **attribute** (legitimate) or to **dismiss** (not legitimate)?
4. If it is quiet: verified clean, or never ran?
5. Does my written claim match what I checked, or is it wider? (See `control-scope`'s
   CLAIM-SHAPE rule — a narrowed instrument yields a narrowed claim.)
6. If the control appears not to exist: did I search every ref, or only the tree I have checked
   out? A control living on an unmerged branch protects nothing while looking finished.

## Worked example — the misread this skill exists to stop (2026-08-03)

`scripts/check_provisioning.py` failed in CI. I ran the differential: it failed **identically**
at base and candidate. I wrote "identical at base; local path gap" into a PR body and moved on.

Every part of that differential was correct. The conclusion drawn from it was not:

- The differential proved *I did not cause it*. ✅
- I read it as *therefore it is not a real problem*. ❌ — rule 1.
- The real state: `ModuleNotFoundError: No module named 'app'` at line 30. A genuine defect
  that fails in CI too. `git log -S` put its introduction in the PR merged 20 minutes earlier.
- It was invisible because it is the **fourth** step of its job and had been skipped behind a
  failing lint step, then a failing test step — rules 2 and 3.
- It had therefore **never executed in CI**. Its silence was unknown state, not clean state —
  rule 4. Once bootstrapped it ran and reported `scanning 520 files across 4 globs`, meaning
  the banned-token gate had been protecting nothing.

Four rules, one failure, and the differential I trusted was the thing that hid it.

## Sibling

Write path — designing a control so it *can* fail, canary placement, claim-shape: see
`control-design`. Claiming your own work is done: see `proof-discipline`.
