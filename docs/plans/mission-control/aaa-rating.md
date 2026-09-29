# Mission Control control set (MC track) — Levels 1–3

**Status:** PROPOSED (r3, 29 Sept 2026). **Grade authority:** the portfolio AAA rubric in
NEXUS-RELEASE-HARNESS v1.0 `scoring.md` ([adoption decision O1](../nexus-release-harness/adoption.md)).
This file no longer defines its own AAA: it defines the MC track's **control set** — the checks
that the portfolio rubric scores — grouped in Levels 1–3 (formerly tiers A/AA/AAA, renamed so
"AAA" has one meaning).

r1 background (28 Sept 2026). Written because no rating scheme for Mission Control
exists: the 19 Sept readiness plan says "No honest production-ready 100/100 score is supportable"
and "never manufacture a readiness score" (`docs/plans/mission-control-readiness.md:32,85`). This
definition keeps that rule — every grade below is a set of pass/fail checks run against a named
deployment, never a model's opinion or a percentage.

The only "AAA" is the portfolio grade. Levels 1–3 here are necessary for it, not sufficient (see
below). Neither is WCAG AAA, which the repo uses elsewhere for contrast and touch targets; WCAG 2.2
AA is one input to Level 2.

## How these checks feed the portfolio AAA rubric

| MC check | Portfolio dimension (weight) | Harness test |
|---|---|---|
| 1 Renders real data · 3 Write actions complete · 12 Label honesty | Customer promises and end-to-end outcomes (25) | T06 (success reply without the intended effect fails) |
| 2 No hidden refusals | Integrations and data integrity (20) | T06 |
| 6 Auth boundary | Security, access and privacy (20) | — (T05 covers mandates at side effects, not page auth) |
| 5 Failure path · 10 Stable | Reliability, recovery and operational support (15) | — |
| 8 Accessibility · 9 Two viewports | Usability and accessibility (10) | — |
| 4 Receipt · 7 Component test · 13 Live-deploy linkage | Evidence provenance, reproducibility, release discipline (10) | T03 (evidence for a different SHA is stale) |
| 11 Nothing documented broken | Mandatory blocker — outside the score | — |
| The level rule below (every check must pass; no evidence = not passed) | Mandatory blocker | T13 (a required unknown cannot become PASS or AAA) |

**Required by the portfolio rubric but not yet in this control set** (added as MC control groups,
each currently NOT_RUN): tenant/object access and OWASP ASVS-selected controls beyond the auth
redirect; two separate non-author audits of the same final candidate (Claude lane + OpenAI/Codex
lane, with provider/model/session receipts); support ownership (RANA identity, rota, backup);
a tested recovery path; the MC Customer Promise Register (each nav blurb and button label is a
promise to the founder). Until these exist, MC cannot score 100/100 and cannot be AAA-RELEASE-READY,
whatever Levels 1–3 show. AAA-LIVE-VERIFIED additionally needs authorised promotion and
deployed-artifact readback (check 13 is the MC part of that).

## The rule that makes it honest

A surface reaches a level only when **every** check in that level passes for it, on the **deployed**
site, on the **current production revision**, in the **latest scheduled run**. One failing check
drops that surface to the level below. Mission Control's level is the **lowest** level of any of its
20 register rows ([coverage-register.md](coverage-register.md)) — one broken page cannot be averaged
away by nineteen good ones.

Jev results never count toward a level or the portfolio score (see [jev-decision-contracts.md](jev-decision-contracts.md)).
They are advisory triage that tells the repair loop where to look.

## Level 1 — it works for a user

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

## Level 2 — it fails honestly and is built to last

Level 1, plus:

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

## Level 3 — it stays working without anyone watching

Level 2, plus:

10. **Stable.** The full suite has passed on production on **three consecutive scheduled runs**
    (nightly), with zero retries used.
11. **Nothing documented broken.** No open CONFLICTING or STRUCTURAL_ONLY row in the register, and
    no open ticket tagged to a Mission Control surface as a defect.
12. **Label honesty.** For every write action, the network calls observed match what the button's
    label claims (e.g. "GO" when "Nothing has started" must not trigger a build). Checked by a
    deterministic assertion on the recorded requests; Jev contract J3 only pre-screens.
13. **Live-deploy linkage.** The run's receipt names the same SHA as the production deployment it
    tested, and the scorecard is published where Phill can see it (one row per surface, with the
    level and the failing check if any).

## Size of the suite this implies

A surface-by-check matrix, not a count chosen to sound large: 20 surfaces × (checks 1, 2, 5, 6,
8 × 2 viewports) ≈ 200 browser journeys, plus 7 write-action journeys (check 3), plus per-panel
component tests (check 7), each journey carrying several assertions. Every journey also produces
the text snapshot that Jev contracts J1–J3 read, so a nightly run yields roughly 200–600 Jev calls.

## What today's grade is

**Ungraded — below Level 1**, so not scoreable under the portfolio rubric. Check 1 is now measured
(29 Sept): components mark the element they render only from backend data with `data-mc-data`,
or an honest empty state with `data-mc-empty` and the reason, and `dashboard/e2e-live/real-data.ts`
asserts one is visible. Three surfaces show no backend data by design, so they fail check 1 until
that is decided: MC-07 (the build form fetches nothing until a run starts), MC-13 (a static index
of links) and MC-14 (a static design-target registry). Check 7 is measured too: each page's data
panels are listed in `dashboard/e2e-live/panel-coverage.json`, and a page passes only when every
panel has passing tests named for its loaded, empty and error states (a page with no data panels
is N/A, which does not count as met). The scorer
(`scripts/mission_control_scorecard.py`) reads the result from the nightly receipts; run the live
suite for today's per-surface levels rather than trusting a count here. Check 10 is measured from
30 Sept: each run's `scorecard.json` records, per surface, whether every live receipt it should
have exists and passed, and is kept 90 days as the `mission-control-scorecard` artifact. The next
run downloads the last three scheduled runs' scorecards and a surface meets check 10 only when the
last three scheduled runs all passed for it on their first attempt
(`scripts/mission_control_stability.py`). A scheduled run that left no scorecard breaks the streak,
and a manual run never counts toward it. Scheduled runs before this change recorded no scorecard,
so check 10 reads "not measured" until three nightly runs have run with it. Check 11 is measured too
(`scripts/mission_control_register.py`): a surface fails when its row in
[coverage-register.md](coverage-register.md) is CONFLICTING or STRUCTURAL_ONLY or missing, or when
an open Linear issue labelled `mc-defect` names it as `MC-xx` (an issue naming no surface counts
against all of them). Without `LINEAR_API_KEY` the ticket half is unread and check 11 reads "not
measured". Check 12 is measured for MC-03 from 30 Sept
(`dashboard/e2e-writes/`, a receipt named `MC-03-W.json`): the real dashboard build runs on the test
machine against a recording stand-in backend, and five journeys assert that what each swarm
button sends matches its label: Halt sends one kill and no resume, Resume the reverse, Cancel and
an invalid form send nothing, and a refused halt is shown and never looks halted. Each journey was
mutation-checked against the real panel code. It proves what the dashboard sends, not that the real
backend accepts it. Every other write surface (MC-01, 02, 05, 07, 10, 11) reads "not measured" for check 12 until
its own journeys exist. **Check 3 stays unmet on all seven write surfaces**: it is defined as running
against a PR preview (Railway `Pi-Dev-Ops-pr-<n>` + Vercel preview), and Vercel's sign-in
protection (`ssoProtection: all_except_custom_domains`, read from the project on 29 Sept) blocks
the browser from previews. **A bypass secret alone is not enough, and by itself it would be unsafe:**
the Vercel variable `PI_CEO_URL` is set to the production Railway URL for the `preview` scope as
well as `production` (a plain, non-secret value, read 29 Sept), so a preview talks to the real
backend, not to the Railway `Pi-Dev-Ops-pr-<n>` copy. `PI_CEO_PASSWORD`, `DASHBOARD_PASSWORD` and
`KILL_SWITCH_SECRET` are production-only, so a preview today would mostly fail closed by accident.
No write journey may be pointed at a preview until previews have their own backend URL and
credentials. That is a founder decision (secrets, and a Railway PR environment per preview).
