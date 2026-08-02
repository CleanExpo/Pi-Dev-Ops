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

### The same rule applies to claims ABOUT EXISTING CODE, not only to specs

**Write a reachability claim as a LOCATION, never as an ABSENCE.**

The unbounded-negative trap is usually filed as a spec-writing error. It is not — it is a
claim-*shape* error, and it bites just as hard when describing code that already exists.

| Unbounded — do not claim | Bounded — claim this |
|---|---|
| "the vault is not reached from the repository" | "the vault is reached from exactly the POST registration path, and nowhere else" |
| "nothing writes to this table" | "the only writer is `recordUsage()` at repository.ts:137" |
| "this route has no auth dependency" | "auth enters at proxy.ts's PROTECTED_API_PREFIXES, and only there" |

**Why the absence form fails.** "Not reached from here" invites *"what about a view? an RPC? a
trigger? a helper you did not open?"* — and the reviewer is right to keep asking, forever.
Nothing you produce settles it. The location form is decidable: go to the named place, confirm
it is the reacher, confirm the search that found it was exhaustive. It is also **re-verifiable
later by someone who was not there**, which an absence never is.

**Worked example, 2026-08-02.** Reviewing the providers port, the builder claimed
*"`credentials_vault` appears nowhere in `repository.ts`"* and traced it honestly. The reviewer
agreed **and improved it**: the vault is reached **only by the POST registration path**
(`provider-accounts/route.ts:69`), never by GET. Same underlying fact, strictly stronger claim —
it names where the capability lives instead of one place it does not.

**Treat a negative reachability claim in a brief as a SPEC DEFECT** and rewrite it before the
review runs, exactly as you would an unbounded negative in a requirement. A reviewer that fails
you for it is correct, and the attempt was spent on the shape of a sentence rather than on code.

*Earned 2026-08-01: three bounded attempts at capability 1 of the command-centre migration were all correctly failed by cross-vendor review, because the spec asked for absolute read-only proof. The code was fine every time. The spec was the defect.*

## A review is never coverage

**A person-shaped or model-shaped check is never a control. This review does not appear in any coverage map, threat model, or assurance argument as a line item.**

Reviews are judgement applied once, by an agent that may be tired, rushed, differently briefed, or simply not looking at the right file that day. A control is a mechanism that fires every time, the same way, whether or not anyone remembers it. Those are different kinds of thing and must never be summed into the same table.

The failure this prevents is specific and seductive: you enumerate ten gaps, note that "cross-vendor review would probably catch most of these", and the gaps stop feeling urgent. Nothing was built. Coverage went down while the document said it went up.

**Rules:**
- Never list a review — human or model — as a row in a coverage map.
- Never justify not building a check on the grounds that review would catch it.
- When a review finds something a control could have found, that is evidence the control is **missing**, not evidence the review is sufficient.
- A gap found by review and left unbuilt is still an open gap. Record it as one.

*Source: Codex (gpt-5.5), auditing this estate's own harness coverage map, 2026-08-01. The map listed cross-vendor review as check "C8" alongside eight mechanical checks. The correction was one line — **"C8 should not be treated as coverage"** — and it invalidated the map's own arithmetic. It was right. Counting the reviewer as a control is how a gap gets closed on paper and left open in fact.*

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
