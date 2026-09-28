# Mission Control — plan to done

**Planning status:** REVIEW_READY for WP-01 (shipped with this packet); BLOCKED-EXTERNAL for live
Jev use and for the deployed browser suite (secrets and network, below). **Plan revision:** r1,
28 Sept 2026. **Inspected revision:** `e3ea829` (main). Written with the `plan-to-done` v1.1
procedure ([candidate package](../plan-to-done-v1.1/plan-to-done/SKILL.md)), followed by hand — the
skill itself is not installed.

## Operator brief

- **Written:** [coverage-register.md](coverage-register.md) (all 20 screens and their real evidence),
  [aaa-rating.md](aaa-rating.md) (what AAA means, as pass/fail checks),
  [work-packages.md](work-packages.md) (12 ordered steps),
  [jev-decision-contracts.md](jev-decision-contracts.md) (exactly what Jev is asked),
  [handoff.json](handoff.json).
- **Fixed in this change:** two screens that could never have worked — `/control/margot` and the
  live detail on `/control/pipeline` — because the dashboard's proxy refused every call they made.
- **Grade today:** ungraded, below A. Not because pages are known broken, but because no test has
  ever opened one in a browser and checked what a user sees.
- **Blocked on Phill:** add `DASHBOARD_PASSWORD` and `TYPESAFE_API_KEY` as GitHub Actions secrets,
  and/or allow `api.typesafe.ai` in this cloud environment; decide D0 (merge authority).
- **Next:** WP-02 (browser sign-in to the deployed dashboard), then WP-06 (read journeys, 20 screens).

## Intent (Capture Intent contract)

The accepted outcome already exists and is referenced, not rewritten:
*"The user's target is a single place to assign an outcome and have the ecosystem execute it
autonomously. Coverage means every built capability is registered, reachable, tested and available
when relevant to a mission."* (`docs/plans/mission-control-jev-next-five.md:29`).

- **Problem.** Mission Control's 20 surfaces carry ≈440 mocked unit tests and live status-code
  smoke, but no test observes what a signed-in user sees. Two panels were silently refused by the
  proxy with no test noticing. There is no agreed meaning of "finished".
- **Proposed outcome.** Every surface reaches AAA as defined in [aaa-rating.md](aaa-rating.md),
  proven nightly on production, with Jev triaging the results at volume.
- **Affected users and systems.** Phill (sole operator); `dashboard/` (Vercel), `app/server/`
  (Railway), `.github/workflows/`, `.github/smoke-surfaces.json`.
- **Constraints.** No new spend beyond the $5/day metered ceiling (Jev estimate $0.20–$1.70/day);
  write-action tests run against PR previews, not production; Jev never decides a grade; CLAUDE.md
  surface-treatment rule (RA-1109).
- **Open questions.** D0 merge authority (Phill). Whether RA-7264 is fixed (evidence gap, WP-04).
  What `/api/zte/score` should be (evidence gap, WP-03).

## Conflicts found in existing plans (recorded, not resolved here)

From the 19 Sept readiness docs and older plans: test counts disagree (4,050 vs 6,561 backend;
236 vs 503 dashboard); "nothing deployed" vs deployments recorded; `.harness/shelf-audit-2026-09-19.md`
is referenced but absent; RA-7264 listed open in QUEUE.md while later handoffs report the gate READY.
Today's measured counts are in [coverage-register.md](coverage-register.md).

## Review record

- Self-check against the writing contract: done. **Not** an independent review.
- Cross-model review (Codex): NOT_RUN — no Codex CLI in this container.
