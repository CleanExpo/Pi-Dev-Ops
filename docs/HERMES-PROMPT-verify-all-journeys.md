# Hermes instruction — verify ALL core journeys in one autonomous run

Replaces the one-journey-at-a-time drip. The agent works through every UNKNOWN journey in
priority order without waiting for you between them, under the approved scoped-write exception,
and produces ONE consolidated honest coverage report. Per-step verification stays (good
discipline); the human round-trip-per-journey is gone (it was never necessary).

---

```
MISSION (Unite-Hub): Verify EVERY currently-UNKNOWN user journey, autonomously, in ONE run,
in priority order. Do NOT wait for human input between journeys. If one journey is blocked,
log it and MOVE ON to the next — never halt the whole run on a single blocker. No new features.
Branch: feat/verify-core-journeys. Open ONE PR. Never push to main.

AUTHORIZATION (scoped, reversible — Phill approved)
Create + delete uniquely-tagged THROWAWAY test data only: test auth users (admin API, email_confirm),
their workspaces, contacts, campaigns, uploads. CRUD on those, then delete ALL with verified cleanup.
NOT allowed: touching pre-existing rows, schema changes, deploys, billing, secret exposure, sending real
emails to real addresses, or completing OAuth consent for a real third-party account.

ENVIRONMENT & KEY SOURCING:
- Load normal env from process env then .env.local; verify by EFFECT, never by reading values; prod host expected.
- To get SUPABASE_SERVICE_ROLE_KEY (needed to provision/delete throwaway test users): do NOT use
  `vercel env run`/`vercel env pull` — Vercel returns sensitive values EMPTY by design, which is why it looks
  absent. Fetch real keys from the Supabase CLI (as the earlier successful run did):
    supabase projects api-keys --project-ref lksfwktwtmyznckodsau --output-format json
  Parse `service_role` + `anon`; use IN-MEMORY only; never print/log/commit. If the Supabase CLI is not
  authenticated, STOP and say so (one human step: `supabase login` or set SUPABASE_ACCESS_TOKEN), then retry.
  Do NOT report the key as missing without trying the Supabase CLI first.
- Self-provision throwaway test users via the service_role admin API. Never print/commit secrets.

SAFETY ENVELOPE: tag all test data ("__PW_TEST__<ISO>" / "playwright+<journey>+<ISO>@unite-hub.test",
non-deliverable). Touch only rows you created. Cleanup mandatory, runs even on failure; re-query and assert
gone; leftovers -> DECISIONS_NEEDED.md with exact IDs. One write-change at a time; re-run its check after each.

HONESTY CONTRACT: report only VERIFIED facts with evidence (HTTP status+body / test output). No "works/done/tick"
without re-run proof. Unverifiable or human-gated -> UNKNOWN with the reason. Green build != working. Append EVIDENCE.md.

JOURNEYS (do in this order; each: prove end-to-end as a real authed user, leave a Playwright e2e guard):
1. Contact CRUD + cross-user RLS isolation (create users A & B; prove create/list/update/delete; A cannot see B).
2. Integrations status (GET integrations list/status as authed user; assert correct shape). Read-only.
3. Lead scoring (seed a test contact with known signals; run the scoring path; assert score matches the rule).
4. Drip campaign (create campaign -> add step -> enroll a TEST contact -> process_pending). Use only the
   non-deliverable test domain; do NOT send to any real address. If a step would email a real provider, mark
   that sub-step UNKNOWN and continue.
5. Multimedia upload + transcription (upload a tiny test file; run transcription). Note: transcription calls a
   paid external API — use the smallest possible sample; if cost/credentials block it, mark UNKNOWN, continue.
6. Gmail OAuth -> import -> contact creation. The OAuth CONSENT step needs a human + a real Google account and
   CANNOT be done autonomously — verify everything around it (endpoints exist, callback handler, sync logic with
   a test/mock token if available), mark the consent step UNKNOWN, and write what Phill must do in DECISIONS_NEEDED.md.

TEARDOWN: delete every test user/workspace/contact/campaign/upload; re-query; assert all gone; record proof.

OUTPUT (one PR):
- COVERAGE.md: each journey = PASS / FAIL / UNKNOWN with evidence links + an overall verified % (UNKNOWN excluded).
- STATUS.md: what genuinely works, what's broken, what's human-gated and the exact action needed, top 3 next fixes.
- EVIDENCE.md, DECISIONS_NEEDED.md, e2e specs (self-cleaning), fixes as small proven commits.

PRINCIPLE: prove each journey as a real user with tagged throwaway data and clean it up — or mark UNKNOWN.
Keep going through ALL journeys; the run ends only when every journey has been attempted and reported.
```

---

When it returns, read COVERAGE.md first: each journey PASS/FAIL/UNKNOWN + an overall %. The UNKNOWNs
that say "needs human" (Gmail consent especially) are the only things that should come back to you —
everything else it either proved or honestly couldn't. Spot-check one PASS by re-running its e2e spec.
