# Hermes instruction — Contact CRUD (option B + self-provisioned test users)

The agent correctly stopped because no test login exists. This version removes that manual
step: the agent provisions throwaway test users itself (Supabase admin API, auto-confirmed,
non-deliverable @unite-hub.test domain), uses them, and deletes them in teardown. It can now
also prove cross-user RLS isolation for real.

This EXTENDS the approved scoped write to include creating + deleting up to two throwaway
test auth users. Reversible and cleaned up. If you'd rather not, use the manual route at bottom.

---

```
MISSION (Unite-Hub): Prove FULL authenticated Contact CRUD (incl. cross-user RLS isolation) using the
SCOPED, REVERSIBLE production-write exception Phill approved. No new features.
Branch: feat/verify-contact-crud. Open a PR. Never push to main.

AUTHORIZATION (scoped, reversible — the only prod writes allowed)
Create and delete uniquely-tagged THROWAWAY test data ONLY: up to TWO test auth users (via Supabase
admin API with email_confirm), their test workspaces, and test contacts; CRUD on those rows; then delete
ALL of it with verified cleanup. NOT allowed: touching any pre-existing row, schema/migration changes,
deploys/promotions/aliases, billing, secrets exposure, or sending real emails.

ENVIRONMENT (do not nag)
- Load env from existing config (process env, then .env.local). Verify by EFFECT, never by reading values.
  Production Supabase host is expected for this exception. You do NOT need pre-set PLAYWRIGHT_TEST_* vars —
  you will create the test user yourself. Never print/commit secret values.

SAFETY ENVELOPE (mandatory — live DB)
- Tag everything: emails "playwright+crud+<ISO8601>@unite-hub.test" (non-deliverable), workspaces
  "__PW_CRUD_TEST__<ISO8601>". Record every created user/workspace/contact ID in EVIDENCE.md on creation.
- Touch ONLY rows you created this run. Generate a strong random password in memory; never log it.
- Watch for unexpected side effects (welcome emails, webhooks) and report any. The test domain is non-deliverable.
- CLEANUP IS MANDATORY, runs even on failure (teardown/finally): delete contacts, workspaces, AND the test
  auth users; then RE-QUERY and assert all are gone; record proof. If cleanup can't finish, write exact
  leftover IDs to DECISIONS_NEEDED.md.

HONESTY CONTRACT
- Report only what you VERIFY with evidence (HTTP status + body, or test output). No "works/done/tick"
  without re-run proof. Unverifiable -> UNKNOWN. A green build is NOT proof. Append-only EVIDENCE.md.

PLAN
1. PROVISION: create test user A via admin API (email_confirm true), then a tagged workspace for A. Record IDs.
2. AUTH: log in as A; create Playwright storage state.
3. PROVE CRUD as A (authed session, NOT service-role): create tagged contact -> 2xx + row; list -> appears,
   scoped to A's workspace; update -> persists on re-read; delete -> gone. Record status+body each.
   Fix any failure one change at a time, proven failing->passing.
4. RLS ISOLATION: create test user B + workspace + contact; assert A CANNOT see B's contact and vice versa.
5. TEARDOWN: delete all test contacts, workspaces, and users A & B; re-query; assert everything removed. Record proof.
6. GUARD: commit a self-contained, self-cleaning Playwright e2e spec (provision -> assert -> cleanup),
   wired so failure is a red gate.
7. STATUS.md: Contact CRUD = PASS/FAIL with evidence; RLS isolation = PASS/FAIL; cleanup verified; recommend
   next journey (Gmail import). No optimistic rounding.

DELIVERABLES: e2e spec, EVIDENCE.md, STATUS.md, DECISIONS_NEEDED.md, fixes as small proven commits.
PRINCIPLE: create only tagged throwaway data, prove it as a real user, delete it and verify removal — or mark UNKNOWN.
```

---

Manual route (if you don't want the agent creating users): Supabase dashboard -> Authentication ->
Users -> Add user -> email + password, tick auto-confirm -> set PLAYWRIGHT_TEST_EMAIL and
PLAYWRIGHT_TEST_PASSWORD in .env.local and Vercel -> use the prior prompt version.

When it returns: STATUS.md should show CRUD = PASS and RLS = PASS with evidence, and teardown
must confirm every test user/workspace/contact was removed (re-query proof). Leftovers, if any,
land in DECISIONS_NEEDED.md with exact IDs.
