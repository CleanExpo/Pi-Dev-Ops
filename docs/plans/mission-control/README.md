# Mission Control — plan to done

**Planning status:** REVIEW_READY for WP-01 (shipped with this packet); BLOCKED-EXTERNAL for live
Jev use and for the deployed browser suite (secrets and network, below). **Plan revision:** r3,
29 Sept 2026 (r1 28 Sept; r2–r3 fold in the portfolio packet). **Inspected revision:** `e3ea829` (main). Written with the `plan-to-done` v1.1
procedure ([candidate package](../plan-to-done-v1.1/plan-to-done/SKILL.md)), followed by hand — the
skill itself is not installed.

**Layer:** this folder is the **MC track** of the portfolio harness NEXUS-RELEASE-HARNESS v1.0.
How it fits, and what the packet replaced here, is in
[nexus-release-harness/adoption.md](../nexus-release-harness/adoption.md).

## Operator brief

- **Written:** [coverage-register.md](coverage-register.md) (all 20 screens and their real evidence),
  [aaa-rating.md](aaa-rating.md) (the MC control set — the pass/fail checks the portfolio AAA rubric scores),
  [work-packages.md](work-packages.md) (12 ordered steps, plus the packet's P-chain),
  [jev-decision-contracts.md](jev-decision-contracts.md) (exactly what Jev is asked),
  [promise-register.md](promise-register.md) (33 promises the screens make, 0 proven yet),
  [handoff.json](handoff.json). The /spm v2.0 mission design is adopted as this track's entry
  point in [adoption.md O10–O17](../nexus-release-harness/adoption.md).
- **Fixed in this change:** two screens that could never have worked — `/control/margot` and the
  live detail on `/control/pipeline` — because the dashboard's proxy refused every call they made.
- **Grade today:** ungraded — below Level 1 of the MC control set. Not because pages are known broken, but because no test has
  ever opened one in a browser and checked what a user sees.
- **Blocked on Phill:** add `DASHBOARD_PASSWORD` and `TYPESAFE_API_KEY` as GitHub Actions secrets,
  and/or allow `api.typesafe.ai` in this cloud environment; decide whether "no Jev cap" overrides
  the packet's budget rule (adoption.md O5).
- **Next:** WP-02 (browser sign-in to the deployed dashboard), then WP-06 (read journeys, 20 screens).

## Intent (Capture Intent contract)

The accepted outcome already exists and is referenced, not rewritten:
*"The user's target is a single place to assign an outcome and have the ecosystem execute it
autonomously. Coverage means every built capability is registered, reachable, tested and available
when relevant to a mission."* (`docs/plans/mission-control-jev-next-five.md:29`).

- **Problem.** Mission Control's 20 surfaces carry ≈440 mocked unit tests and live status-code
  smoke, but no test observes what a signed-in user sees. Two panels were silently refused by the
  proxy with no test noticing. There is no agreed meaning of "finished".
- **Proposed outcome.** Every surface reaches Level 3 of the MC control set in [aaa-rating.md](aaa-rating.md), and the MC release earns AAA under the portfolio rubric,
  proven nightly on production, with Jev triaging the results at volume.
- **Affected users and systems.** Phill (sole operator); `dashboard/` (Vercel), `app/server/`
  (Railway), `.github/workflows/`, `.github/smoke-surfaces.json`.
- **Constraints.** Jev daily cap lifted by founder decision 28 Sept (spend still ledgered; estimate $0.20–$1.70/day) —
  conflicts with the packet's recorded-budget rule, open (adoption.md O5), so Jev runs dry until settled;
  write-action tests run against PR previews, not production; Jev never decides a grade; CLAUDE.md
  surface-treatment rule (RA-1109).
- **Open questions.** Whether RA-7264 is fixed (evidence gap, WP-04). *Resolved since r1:* D0 merge
  authority — human merge (RA-7818); `/api/zte/score` — serves the daily cron's cached score (WP-03, #818).

## Conflicts found in existing plans (recorded, not resolved here)

From the 19 Sept readiness docs and older plans: test counts disagree (4,050 vs 6,561 backend;
236 vs 503 dashboard); "nothing deployed" vs deployments recorded; `.harness/shelf-audit-2026-09-19.md`
is referenced but absent; RA-7264 listed open in QUEUE.md while later handoffs report the gate READY.
Today's measured counts are in [coverage-register.md](coverage-register.md).

## Review record

- Self-check against the writing contract: done. **Not** an independent review.
- Cross-model review (Codex): NOT_RUN — no Codex CLI in this container.
