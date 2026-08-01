---
name: adversarial-review
description: Review a proposed fix with a different model in a fresh session that has no access to the builder's reasoning. Two axes, standards and spec, run as independent sub-agents. It flags; it never fixes. A fail returns to `propose-fix`. Use after `propose-fix`, before anything is applied.
---

# adversarial-review

**The point is separation of model and context, not roleplay.** The reviewer is a sub-agent given a narrow brief and a fixed input set. It is not a persona, has no name, and is not asked to act like a senior engineer. Do not write character instructions.

The value comes from what the reviewer **cannot see**: the builder's reasoning, its hypotheses, its rejected approaches, and its confidence. A reviewer that inherits the builder's context inherits its blind spots and will agree with them fluently.

Dual-axis structure adapted from `code-review` (mattpocock/skills).

## Spec-writing standard — read before writing the spec

**Never write a spec item that asks a reviewer to prove an unbounded negative.**

"Proves this page makes no network call" is unbounded. There is always another path — a dynamic import, `require`, `WebSocket`, `EventSource`, `sendBeacon`, a server action, a transitive side-effect import. A competent reviewer will keep finding them, correctly, forever. The builder cannot win and the reviewer is not wrong.

**Write bounded, diff-relative claims instead.**

| Unbounded — do not write | Bounded — write this |
|---|---|
| "makes no network call" | "introduces no network surface the source did not have" |
| "is read-only" | "adds no write path absent from the baseline" |
| "has no side effects" | "the diff adds no side-effect construct not already present" |

A diff-relative claim is decidable: compare the change against a named baseline and the answer is yes or no. An absolute claim is not.

**A diff-relative claim is only as strong as its baseline.** Where the baseline's own safety properties are load-bearing — an execution surface, a payment path, an approval gate — establish the baseline **by hand, once, before the port**, and cite that record in the spec. Otherwise "no new surface" inherits whatever the source already had, unexamined.

*Earned 2026-08-01: three bounded attempts at capability 1 of the command-centre migration were all correctly failed by cross-vendor review, because the spec asked for absolute read-only proof. The code was fine every time. The spec was the defect.*

## Phase 1 — Assemble the input set

The reviewer receives **exactly these four things** and nothing else:

1. **The spec** — the originating issue, requirement, or stated intent
2. **The failing loop** — the command from `prove-the-failure` and its red output
3. **The diff** — the proposed change
4. **The test** — the regression test and its observed failure

**Do not include:** the diagnosis narrative, the ranked hypotheses, the rejected approaches, the attempt number, or any statement of how confident the builder is. Those are exactly the contaminants.

Use a different model from the one that produced the fix. Same model, fresh session, is a weaker control and must be recorded as such.

## Phase 2 — Two independent sub-agents

Send one message with two `Agent` calls. They do not see each other's output.

**Standards sub-agent brief:**
> Review this diff against the repository's documented coding standards, then against the baseline smells. Cite the source for each documented violation and quote the hunk for each smell. Distinguish hard violations from judgement calls. Skip anything tooling already enforces. Under 400 words.

**Spec sub-agent brief:**
> Review this diff against the spec and the failing loop. Report: (a) requirements missing or incomplete; (b) behaviour introduced that was not asked for; (c) requirements implemented incorrectly; (d) whether the test would actually catch the failure the loop demonstrates, or merely passes alongside it. Quote the spec for each. Under 400 words.

Item (d) is the one that catches the expensive mistake: a test that passes for the wrong reason and locks in a fix that does not work.

## Phase 3 — Consolidate

Present findings under `## Standards` and `## Spec` without merging or reordering. The axes stay independent — merging them lets a weak finding on one borrow credibility from the other.

Close with one line: count per axis, and the single most serious finding in each.

## Verdict

| Verdict | Meaning | Next |
|---|---|---|
| **PASS** | No hard violations; no missing or incorrect requirements; test genuinely catches the failure | `verify` |
| **FAIL** | Any hard violation, missing requirement, unasked-for behaviour, or a test that does not catch the failure | back to `propose-fix` |

A FAIL consumes an attempt from `propose-fix`'s bound of three.

**Reviewer silence, timeout, or crash is not a pass.** Convergence requires an explicit, evidence-backed verdict. If the reviewer did not return one, the review did not happen.

## Completion

- [ ] Reviewer model named, and confirmed different from the builder's
- [ ] Input set limited to the four items — confirmed, not assumed
- [ ] Both sub-agents returned, or the missing one is recorded as a gap
- [ ] Findings presented per-axis, unmerged
- [ ] Explicit verdict recorded

## Stop conditions

**The reviewer flags; it does not fix.** A reviewer that returns a diff has exceeded its brief — discard the diff and keep the finding.

**Do not argue with a FAIL.** Return to `propose-fix` and change the approach. Re-running the same review hoping for a different verdict is the reasoning-erosion pattern the fence exists to prevent.

## Next

`verify` on PASS. `propose-fix` on FAIL, attempt count incremented.
