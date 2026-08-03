# Inner loop — self-improvement inside the fence

The orchestrator audits itself against the constitution, trims its own bloat, catches its own
hallucinations, and tightens how it writes code. Every fix stays inside the fence. Fixes that would touch
money or production stop and ask. Every self-modification is logged for the board.

**A denied action stays denied. No reasoning its way back in.**

---

## 1. When it runs — and an open founder conflict

The brief says "on a cadence." A standing founder constraint says the opposite:

> **UNI-2433 (founder, 2026-07-17):** *"Standing constraint: no calendar timeframes. State-based only —
> phases advance on completion."*

Constitutional Operations §8.1 already flags this and rules that **a ruling is required**: does the
constraint govern *phase advancement only*, or *all timeframes*? It is unresolved.

**Not resolving it silently.** The loop is built **state-triggered first**, which satisfies both readings:

| Trigger | Type | Rationale |
|---|---|---|
| An outer-loop spoke pass completes | state | the natural seam; nothing is mid-flight |
| A stage artifact is written | state | new evidence to audit against |
| A denial is recorded | state | something just hit the fence — learn from it |
| A PR is reverted or a gate fails | state | strongest tightening signal available |
| Idle backstop | elapsed | **only** if nothing above fired; disabled by default |

If the ruling comes back "all timeframes", delete the backstop row and nothing else changes. If it comes
back "phase advancement only", enable it. The design does not depend on the answer.

## 2. Trim — cache and bloat

| Target | Rule | Reversible? |
|---|---|---|
| Stale cache entries | evict past TTL or superseded by newer artifact | yes |
| Merged/abandoned local branches | delete local only, **never remote** | yes |
| Superseded planning artifacts | archive, don't delete — audit trail | yes |
| Duplicate skills | flag for merge; **do not auto-merge** — that is a doctrine change | n/a — propose only |
| Orphaned worktrees | remove if `git status` clean | yes |

**One hard-won caveat, from the estate's own damage record:** never `robocopy /MIR` or bulk-delete across
`node_modules` in a workspace repo — workspace symlinks are followed and real source is destroyed.
Trimming is per-entry and reversible, or it does not happen.

**Bloat in its own skills counts.** A SKILL.md over the 200-line soft cap is usually two skills wearing one
coat. The loop flags it; a human splits it.

## 3. Flag — suspected hallucinations

An evidence gate already exists and already ships: `~/.claude/hooks/Stop/04_evidence_gate.py` blocks
turn-end when a strong completion claim appears in a turn with **zero tool activity**. It is deliberately
conservative and **fails open**.

**That leaves the real gap:** a claim made in a turn that *did* use tools, but where the specific claim has
no result behind it. The gate cannot catch that without unacceptable false positives in a blocking path.

So the inner loop runs the aggressive version **offline**, where a false positive costs nothing:

```
for each completion-shaped claim in recent transcripts:
    find the tool result that would substantiate it
    no result found                     -> SUSPECT
    result exists but contradicts claim -> CONTRADICTED   (worse than suspect)
    result is a null/zero/empty finding
        and no positive control preceded it -> UNCONTROLLED NULL
```

That third class is the estate's most expensive recurring error: `0 findings` from a broken query is
indistinguishable from `0 findings` from a clean system. Any null used as evidence without a positive
control is flagged, not trusted.

Output is **findings, not blocks**: appended to `.harness/self-mods.jsonl` as `flag` entries. The loop does
not get to decide it was wrong about itself — that is self-grading, which Ch2 §3 forbids
(*"a grader under the control of the graded optimises itself"*). It reports; a human or an independent
reviewer adjudicates.

> **Do not "harmonise" the two gates.** The Stop hook fails **open** on purpose — wrongly blocking a turn
> is friction. The fence fails **closed** on purpose — wrongly allowing a prod deploy is unrecoverable.
> Different risk profiles, deliberately different defaults.

## 4. Tighten — code generation

The only honest signal is **what happened to shipped work**, not what the model believed at write-time.

| Signal | Source | Feeds back as |
|---|---|---|
| PR reverted | git history | pattern demoted |
| CI red on first push | Actions | pre-push check added |
| Review finding repeated ≥3× | review records | a lint rule, or a line in the repo's CLAUDE.md |
| Gate rejected the work | `pr-release-gate` | stage checklist item |
| Denial recorded | `denials.jsonl` | classifier predicate refined |

Tightening writes to prompts, skill bodies and repo conventions — all inside the fence, all reversible,
all committed so the diff is reviewable.

**It may not tighten by weakening a gate.** A rule that keeps failing is a finding about the code, not a
reason to lower the bar. Any proposed change to a gate's threshold is a proposal, not a self-fix.

## 5. Log — the paper trail

Every self-modification, one line, append-only:

```jsonc
{ "ts":"2026-08-01T09:14:22Z", "kind":"trim|flag|tighten|propose",
  "target":"skills/foo/SKILL.md", "before_sha":"…", "after_sha":"…",
  "reason":"…", "trigger":"spoke-pass-complete",
  "fence":"inside", "reversible":true, "evidence":"…" }
```

Append-only, per `audit-emit`'s existing `.harness/swarm/swarm.jsonl` pattern — reuse the emitter, don't
build a second one. §6.35 requires the record to distinguish
`attempted · authorised · completed · failed · reversed · simulated · proposed`; the `kind` + outcome
fields carry that.

**Why it must be a file and not a memory:** an unlogged self-modification is indistinguishable from drift.
The board cannot review what was not written down, and "the agent improved itself" with no diff is exactly
the claim the estate has the least ability to check.

## 6. The fence, restated for self-modification

| Action | Verdict |
|---|---|
| Rewrite own prompt / skill body | **inside** — do it |
| Evict own cache | **inside** — do it |
| Delete local branch | **inside** — do it |
| Refactor own heuristics | **inside** — do it |
| Edit `fence.json`, the classifier, or the `PreToolUse` hook | **STOP** — §6.2, no system expands its own permissions |
| Delete a remote branch | **STOP** — irreversible |
| Change a gate threshold | **STOP** — propose only |
| Anything touching a prod host/branch/database | **STOP** |
| Anything that spends | **STOP** |

Self-improvement is not a special category with its own rules. It runs against the same fence as
everything else — that is the entire point of having one fence.

## 7. Denied stays denied

The inner loop is the most likely component to try to reason its way back into a denied action, because
its whole purpose is to improve on prior behaviour. It is therefore explicitly bound:

- A denial fingerprint is checked **before** the loop evaluates the action, not after.
- "I now have a better argument" is not an input. Neither is "conditions changed."
- The loop may record *why* it believes the denial was wrong. It may not act on that belief.
- Only the founder clears a denial, and clearing it creates a **new** record.

A self-improving system that can retire its own constraints is not fenced. It is merely slow.
