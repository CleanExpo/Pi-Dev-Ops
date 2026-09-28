# Mission Control AAA rating — definition

**Status:** PROPOSED (r1, 28 Sept 2026). Written because no rating scheme for Mission Control
exists: the 19 Sept readiness plan says "No honest production-ready 100/100 score is supportable"
and "never manufacture a readiness score" (`docs/plans/mission-control-readiness.md:32,85`). This
definition keeps that rule — every grade below is a set of pass/fail checks run against a named
deployment, never a model's opinion or a percentage.

"AAA" here is a Mission Control grade. It is **not** WCAG AAA, which the repo uses elsewhere for
contrast and touch targets; WCAG is one input to tier AA below.

## The rule that makes it honest

A surface earns a tier only when **every** check in that tier passes for it, on the **deployed**
site, on the **current production revision**, in the **latest scheduled run**. One failing check
drops that surface to the tier below. Mission Control's grade is the **lowest** grade of any of its
20 register rows ([coverage-register.md](coverage-register.md)) — one broken page cannot be averaged
away by nineteen good ones.

Jev results never count toward a grade (see [jev-decision-contracts.md](jev-decision-contracts.md)).
They are advisory triage that tells the repair loop where to look.

## Tier A — it works for a user

For each surface:

1. **Renders real data.** A browser test signs in, opens the page on production, and asserts at
   least one element whose content comes from the live backend (a row, a count, a timestamp) —
   not a placeholder, empty state or error banner. A page whose honest state is "empty" asserts the
   explicit empty-state copy instead, and says why empty is correct.
2. **No hidden refusals.** During that visit, zero requests from the page return 4xx/5xx (excluding
   ones the test deliberately provokes). This is the check that would have caught MC-10 and MC-11.
3. **Write actions complete.** Each write action runs end to end against a PR preview environment
   (Railway `Pi-Dev-Ops-pr-<n>` + Vercel preview), and the result is still visible after a page
   reload. Destructive or outward actions (filing to Linear, killing the swarm, starting a paid
   build) run against preview only, with the side effect asserted and cleaned up.
4. **Receipt.** The run records deployed SHA, URL, time, and pass/fail per check as a JSON artifact.

## Tier AA — it fails honestly and is built to last

Tier A, plus:

5. **Failure path.** With the backend forced unreachable (route intercepted in the browser), the
   page shows an explicit, actionable error — never a spinner that never ends, never stale data
   shown as current. (CLAUDE.md surface-treatment rule: no silent `.catch`, no 3-second toast as the
   only feedback.)
6. **Auth boundary.** Signed out, the page redirects (307) and its APIs refuse (401). Already partly
   in `smoke-surfaces.json`; becomes a browser assertion per surface.
7. **Component test.** Every panel on the page has at least one vitest test covering its loaded,
   empty and error states. Today 8 panels have none.
8. **Accessibility.** An automated axe scan on each page reports zero serious or critical
   violations at WCAG 2.2 AA.
9. **Two viewports.** Checks 1–2 pass at desktop (1440×900) and phone (390×844) sizes.

## Tier AAA — it stays working without anyone watching

Tier AA, plus:

10. **Stable.** The full suite has passed on production on **three consecutive scheduled runs**
    (nightly), with zero retries used.
11. **Nothing documented broken.** No open CONFLICTING or STRUCTURAL_ONLY row in the register, and
    no open ticket tagged to a Mission Control surface as a defect.
12. **Label honesty.** For every write action, the network calls observed match what the button's
    label claims (e.g. "GO" when "Nothing has started" must not trigger a build). Checked by a
    deterministic assertion on the recorded requests; Jev contract J3 only pre-screens.
13. **Live-deploy linkage.** The run's receipt names the same SHA as the production deployment it
    tested, and the scorecard is published where Phill can see it (one row per surface, with the
    tier and the failing check if any).

## Size of the suite this implies

A surface-by-check matrix, not a count chosen to sound large: 20 surfaces × (checks 1, 2, 5, 6,
8 × 2 viewports) ≈ 200 browser journeys, plus 7 write-action journeys (check 3), plus per-panel
component tests (check 7), each journey carrying several assertions. Every journey also produces
the text snapshot that Jev contracts J1–J3 read, so a nightly run yields roughly 200–600 Jev calls.

## What today's grade is

**Ungraded — below A.** Check 1 cannot pass on any surface because no browser test exists
(coverage-register.md: "Browser tests touching any surface: 0"). This is a statement that the
evidence does not exist, not that the pages are broken.
