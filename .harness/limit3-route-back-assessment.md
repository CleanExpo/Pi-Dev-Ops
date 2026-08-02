# Deriving production expectations from the auth classification — assessment (NOT built)

The wider version of the kill-switch proof, and the actual route back from **Structural Limit 3**:
generate production surfaces from `dashboard/__tests__/api-auth-classification.json` instead of
hand-writing them from observed behaviour.

The classification already holds the requirement. Today nothing turns it into a production
assertion — which is exactly how `POST /api/telegram -> 200` sat inside a green production check
for 117 days.

## What it would cover

`api-auth-classification.json` classifies **every** API route, and each classification implies an
unauthenticated expectation that can be generated rather than authored:

| classification | generated production assertion |
|---|---|
| matched by `PROTECTED_API_PREFIXES` | anonymous request -> **401** |
| `route-self-protected` (declared) | anonymous request -> the declared `unauth_status` (401/403) |
| `deliberately-public` (declared) | anonymous request -> the declared success status |
| matched by `PUBLIC_API_PREFIXES` | anonymous request -> not 401 |

**23 API routes today, and the count is DISCOVERED rather than listed** — a route added tomorrow
gets a production expectation without anyone remembering to write one. That is the property that
was missing. The telegram surface existed because someone probed the route and recorded what it
did; a generated surface states what the route is *required* to do.

**It would have caught this incident.** The telegram route's declared classification implies a
refusal for an anonymous caller. The hand-written contract asserted 200. A generated one could
not have.

## What it cannot cover — stated now, not discovered in a later round

- **Authenticated behaviour.** It asserts what an anonymous caller gets. It says nothing about
  whether an authenticated caller gets the right answer.
- **Payload shape.** Public routes assert a status, not contents. Widening is covered separately
  by `public-read-shape.test.ts`, and only for the three routes it knows about.
- **Correct-credential acceptance.** The kill-switch proof exists precisely because a refusal is
  not evidence that the guard accepts a valid credential. Generating that generally would need
  the generator to hold every credential — a worse problem than the one being solved.
- **Non-API surfaces.** Pages are covered by the auth suite against `proxy()` directly, not
  against production.
- **Correctness of the classification itself.** A mis-declared route yields a generated surface
  that faithfully asserts the wrong thing. This moves trust from "whoever wrote the probe" to
  "whoever wrote the classification" — better, because the classification is declared with a
  reason, reviewed, and already has a check that every route carries one. **Not eliminated.**

## What it would take

1. **Generator** (~half a day). Read the classification, parse the `proxy.ts` prefixes, emit
   surface entries. Both halves already exist inside `api-auth-classification.test.ts` and can be
   lifted rather than written.
2. **Decide the join with `smoke-surfaces.json`** — the real design question, not the code.
   Either generated entries are written into that file with a CI drift check (visible, diffable,
   but a generated file living in the repo), or the e2e runner consumes generator output directly
   (no drift possible, but the contract stops being readable in one place).
   **Recommend the first** — a drift check is the same shape as `generated-agentskills`, which
   this repo already understands.
3. **Reconcile the existing hand-written entries — under the constraint below.** Expect
   conflicts, and treat each as a finding: a hand-written expectation that disagrees with the
   classification is either a mis-declared route or another `telegram -> 200`.

   ### THE RECONCILIATION CONSTRAINT — written now, while the reason is fresh

   **Every conflict is adjudicated individually. None is resolved by editing the generated side
   to match observed behaviour.**

   When a generated expectation disagrees with what a route actually does, exactly two
   resolutions are legitimate:

   - **The requirement wins** — the route is wrong and gets fixed. This is the `telegram -> 200`
     case: the classification said refuse, the route served anyone, and the route was the defect.
   - **The classification is corrected** — the declared classification was wrong, and it is
     changed *deliberately, with a reason recorded*, the same way a declared delta is.

   **Forbidden: changing the generated expectation to match what the route does.** That is the
   fast path, it makes the whole suite green in one pass, and it recreates the exact defect this
   work exists to remove — a contract that describes behaviour instead of requiring it. Doing it
   at scale would be worse than never generating anything, because it would launder observed
   behaviour into something that *looks* requirement-derived.

   **Why this warning is here and not left to judgement.** In three weeks this reconciliation
   will look like an ordinary refactor with a large diff and a lot of red. Under that pressure,
   "just make the generated file match reality" is the obvious move and will feel like
   housekeeping. It is not. **A conflict is a finding, and a batch of conflicts is a batch of
   findings, not a formatting problem.** If the volume makes one-at-a-time adjudication
   impractical, that is a signal to stop and escalate — not to switch strategies.
4. **Controls, mandatory per the standard.** A planted mis-declared route must produce a failing
   surface, and an empty generator output must fail loudly rather than assert nothing.

## Risk to weigh before building

This makes `api-auth-classification.json` load-bearing for production assertions. Per the
consolidation rule, a component whose blast radius changes should be **reviewed as new code even
though its contents do not change** — the file becomes trusted by a system that did not trust it
before.
