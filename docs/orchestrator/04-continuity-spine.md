# Continuity spine — idea to ship, without losing the thread

One spine, seven stages. Each stage hands the next a **written artifact, not a memory**. State lives on
the tracker, not in context. A stage cannot open until the one before it left its artifact.

At ship, every requirement from the original idea is marked `built`, `partial`, or `missing`.
**No silent gaps.**

---

## The rule that makes it work

> **Context is assumed lost. The tracker is assumed to survive.**

Everything else follows. If a fact matters after this turn, it is written to Linear or to an artifact file
— never held in the conversation. This is not caution about compaction; it is the design. An orchestrator
that depends on remembering has already failed at the first handoff, which is precisely the estate's
recorded failure mode.

## The seven stages

| # | Stage | Artifact it must leave | Cannot open until |
|---|---|---|---|
| 1 | **idea** | `IDEA.md` — the requirement list, numbered `R1..Rn`, in the requester's words | — |
| 2 | **research** | `RESEARCH.md` — findings + citations + explicit unknowns | `IDEA.md` exists |
| 3 | **scope** | `SCOPE.md` — in / out / deferred, each line tied to an `R#` | `RESEARCH.md` exists |
| 4 | **plan** | Linear issues, one per unit, parented to the epic | `SCOPE.md` exists |
| 5 | **build** | commits + PR, each referencing its issue | plan epic has ≥1 issue |
| 6 | **test** | `TEST.md` — what ran, what passed, **the actual output** | PR exists |
| 7 | **ship** | `COVERAGE.md` — every `R#` marked | `TEST.md` shows a green run |

**`R1..Rn` is the spine's backbone.** Numbering the requirements at stage 1 is what makes the coverage
check possible at stage 7. Without stable IDs, "did we build it?" is a memory question and the thread is
already lost.

## The precondition is a file check, not a judgement

```
open_stage(n):
    artifact = ARTIFACT[n-1]
    if not exists(artifact):        -> BLOCKED. Say which artifact is missing. Stop.
    if exists but empty/stub        -> BLOCKED. A placeholder is not a handoff.
    if exists and non-trivial       -> open stage n
```

**No agent report substitutes for the file.** Per `proof-discipline`: a sub-agent saying "research is
done" is an assertion; `RESEARCH.md` on disk is evidence. The orchestrator checks the disk.

This is also what makes the spine resumable. A cold start on any project reads the artifact directory,
finds the highest stage with a valid artifact, and opens the next one. No handoff document, no session
memory, no "where were we" — the filesystem answers it.

## The plan parks on Linear as the map

Stage 4 is different from the others: its artifact is not a file, it is **tracker state**.

- One **epic** per idea, titled with the idea, body linking `IDEA.md` and `SCOPE.md`
- One **issue** per unit of work, each naming the `R#` it serves
- Issue state is the single source of truth for progress — not a checklist in context, not a TODO comment
- Blocked work carries the blocking reason **in the issue**, so the block survives the session that found it

Team routing follows the existing estate map: `GP-` for CARSI, `RA-` for RestoreAssist, `UNI-` for
Unite-Group/Authority-Site, `SYN-` for Synthex, `DR-` for Disaster-Recovery.

Two known operational traps, already paid for: `list_issues` overflows the tool cap on large boards —
save and parse instead; and label writes **replace the whole set**, so read-modify-write or labels are
silently destroyed.

## Read what you need, write what you learned, release the rest

Each stage:

1. **Reads** only its predecessor's artifact and the tracker — not the whole history
2. **Checks out** only the skills that stage needs (see the orchestrator's stage→skill table)
3. **Writes** its own artifact
4. **Releases** every skill and file it pulled

Step 4 is what allows a seven-stage project to run without any stage inheriting the accumulated weight of
the previous six. A stage that ends still holding its skills has leaked, and the leak compounds — by stage
5 the context is full of stage-1 reasoning nobody needs.

**Compression is a fence event, not a housekeeping event.** §6.40: a compressed context must retain the
objective, authority level, permitted/prohibited actions, spend limits and escalation triggers — and must
never convert *preparation into execution authority* or *a proposal into approval*. Where authority cannot
be reconstructed after compression, the stage **reopens as preparatory** and escalates. It does not guess.

## Ship — the coverage check

The last gate. For every requirement `R1..Rn` from `IDEA.md`:

| Mark | Meaning | Evidence required |
|---|---|---|
| `built` | shipped and verified | the test output, plus the commit/PR |
| `partial` | some of it shipped | what shipped, **and what did not** |
| `missing` | not built | why, and where it went (deferred issue / dropped with reason) |

Rules:

- **Every `R#` gets a mark.** An unmarked requirement fails the check.
- **`missing` is a legitimate outcome.** Dropping scope is fine; dropping it *silently* is not.
- **A requirement nobody can find is `missing`, not "presumably done".** Absence of evidence is `missing`.
- **`partial` must name the remainder**, and the remainder becomes a tracked issue before ship closes.

`COVERAGE.md` is the artifact and it is the thing a human reads to know what they actually got — which is
the only question the whole spine exists to answer.

## Where the spine touches the fence

Six of seven stages are entirely inside the fence: idea, research, scope, plan, build, test. They read,
write, commit, branch, open PRs, file issues — all reversible.

**Ship is the boundary.** Merge to `main`, deploy, migrate — every one is a STOP. So the spine is designed
to run all the way to *"PR open, tests green, coverage written"* **without asking**, and then stop.

That is the maximum finished work that is still fully reversible, and it is where the orchestrator should
land every time. The human's decision is reduced to one question — merge or not — with the coverage table
in front of them.

## Failure handling

| Situation | Behaviour |
|---|---|
| Stage produces no artifact | stage stays open; do not advance; record the blocker on the tracker |
| Artifact exists but is a stub | treated as absent |
| Test stage red | do not advance to ship; the red output *is* `TEST.md`'s content |
| Stage blocked on a gate | record the gate, **move to another spoke**, return when cleared |
| Denial hit mid-spine | terminal for that action; re-scope the stage around it, never retry it |
| Context lost mid-stage | reopen from the last valid artifact — by design, nothing else is needed |

---

*The spine's only claim: after any interruption, the next agent can determine the exact state of the work
by listing a directory and reading a tracker. If that is ever untrue, a stage wrote to context instead of
to disk, and that is the bug.*
