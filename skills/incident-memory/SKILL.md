---
name: incident-memory
description: Write symptom, cause, fix, reviewer verdict and outcome to a searchable store — successes and failures alike. This is the store `classify` reads to decide known versus novel. Use as the final step of every self-healing chain, including chains that stopped early or gave up.
---

# incident-memory

**Every chain writes here. Including the ones that failed.**

A store containing only successes teaches `classify` that everything is known and everything works. The failures — the unproven causes, the exhausted attempt bounds, the loops that could not be built — are what make the known/novel judgement honest.

Store: `.harness/incidents.jsonl`, append-only, one JSON object per line.

## Phase 1 — Write the record

```jsonc
{
  "id": "INC-<UTC timestamp>",
  "ts": "2026-08-01T03:40:00Z",
  "symptom": "what was observed, in the reporter's words",
  "loop": "the exact command from prove-the-failure",
  "loop_built": true,
  "contained": "what was stopped, and its undo",
  "left_alone": "what was deliberately not stopped, and why",
  "cause": "one sentence, plain language",
  "cause_proven": true,
  "evidence": "file:line",
  "rejected": ["hypotheses ruled out, and what ruled them out"],
  "classification": "known|novel",
  "blast_radius": "low|high",
  "blast_reasoning": "what else changes, what that could trigger",
  "attempts": 1,
  "approaches": ["how each attempt differed in kind"],
  "diff": "path to the proposed diff, or null",
  "reviewer_model": "which model reviewed",
  "reviewer_verdict": "PASS|FAIL|ABSENT",
  "reviewer_findings": ["what it flagged"],
  "verified": true,
  "immunisation": "the guard added, or the fence change proposed-unapplied, or none-possible",
  "outcome": "fixed|gave-up|stopped-at-gate|breaker-tripped",
  "gated_on": "what a human must decide, if anything"
}
```

**`outcome` is the load-bearing field.** Its four values are all legitimate:

- `fixed` — verified green, immunised
- `gave-up` — attempt bound exhausted; the diagnosis is the deliverable
- `stopped-at-gate` — `classify` said novel or high-radius, or a gated action was required
- `breaker-tripped` — the chain halted; a human was called

## Phase 2 — Make it findable

`classify` matches on **cause**, not symptom. Write the cause so a later match is possible:

- State the mechanism, not the manifestation. *"Workflow pushes directly to a protected branch"* not *"the drain job failed"*.
- Name the surface concretely — repo, file, job, database.
- Avoid words that only make sense with this incident's context in mind.

Search is `grep` over the JSONL. Do not build an index; the file is small and will stay small, and an index is a second thing that can be wrong.

## Completion

- [ ] Record appended, valid JSON on one line
- [ ] `cause` written as a mechanism, matchable by a future chain
- [ ] `outcome` set to one of the four values
- [ ] Failures recorded with the same care as successes
- [ ] `gated_on` populated whenever a human must act

## Stop conditions

**Never rewrite or delete a prior record.** Append-only. A correction is a new record referencing the old `id`.

**Never mark `outcome: fixed` without `verified: true`.** Applied is not verified; verified means `verify` ran and pasted both outputs.

**This file is not on the self-modification list, but treat it as evidence.** An agent editing its own incident history to make a failure look known is the same class of act as clearing its own denials — if you find yourself wanting to adjust a past record so the current fix qualifies, that is the signal to stop.

## Next

End of chain. If `outcome` is anything other than `fixed`, the report goes to the founder with the diagnosis attached.
