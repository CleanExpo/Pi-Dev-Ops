# Hermes instruction — next targeted build: Lead Scoring API

Why this one: the scoring logic (qualifyLead) already exists and is unit-tested; only the
authenticated route that runs it over a real contact and persists the score is missing. So this
is wiring proven code, not a net-new feature — highest probability of a clean full PASS, and
core to the AI-CRM value. (EV terms: high p_success, real value, low cost, reversible -> top move.)
Do drip / transcription after this clean win. One targeted build at a time beats the broad sweep.

---

```
MISSION (Unite-Hub): Build and PROVE the authenticated Lead Scoring journey end-to-end. ONE target only.
Branch: feat/lead-scoring-api. One PR. Never push to main. No unrelated changes.

CURRENT TRUTH: qualifyLead deterministic scoring logic + unit tests already exist (src/lib/crm). There is
NO authenticated API/app route that runs scoring over a real contact and persists the score. Build that —
reuse the EXISTING qualifyLead library as the single source of truth; do NOT reimplement scoring.

KEY SOURCING: SUPABASE_SERVICE_ROLE_KEY from `supabase projects api-keys --project-ref
lksfwktwtmyznckodsau --output json` (in-memory only; NOT vercel env run). Never print/commit secrets.

SAFETY ENVELOPE: scoped reversible prod TEST data only (tagged throwaway user/workspace/contact), full
verified cleanup. No destructive schema ops, no deploys, no real emails, no billing. One change at a time.
Re-run the existing PASS guards (contact-crud, core-journeys) each cycle so you do not regress them.

HONESTY CONTRACT: PASS only with re-run evidence (HTTP status+body / test output). No "done/tick" without
proof. Unverifiable -> UNKNOWN. Update COVERAGE.md honestly.

BUILD
1. Add an authenticated endpoint (repo convention, e.g. POST /api/contacts/score) that: loads a contact the
   caller is authorized for, runs qualifyLead over its real signals (engagement/sentiment/intent/title/status
   per the documented weights), and PERSISTS the result to contacts.ai_score. Authorized + RLS-scoped only.

PROVE (end-to-end, as a real authed user)
2. Provision a tagged test user + workspace + a contact with KNOWN signals.
3. Compute the EXPECTED score from qualifyLead's rule for those signals.
4. Call the endpoint as the authed user -> assert 2xx, and assert the PERSISTED ai_score == expected score
   (re-read the row to confirm it saved). Record request + status + body.
5. Assert scoping: the caller CANNOT score a contact in another workspace (create a second tagged workspace/contact).
6. TEARDOWN: delete all tagged test data; re-query; assert gone. Record proof.

GUARD: commit a self-cleaning Playwright e2e spec for this journey, wired so failure is a red gate.

OUTPUT (one PR): updated COVERAGE.md (Lead scoring = PASS with evidence), STATUS.md, EVIDENCE.md,
DECISIONS_NEEDED.md (if anything blocks), small proven commits.

PRINCIPLE: reuse the proven scoring logic, prove the persisted score matches the rule for a real authed user,
clean up — or mark UNKNOWN. Build only this journey.
```

---

Judge it: COVERAGE.md should flip Lead scoring to PASS with evidence that the persisted ai_score matches
the rule's expected value. Re-run the new e2e guard yourself. Then the next targeted build is Drip campaign
(net-new lifecycle — bigger), or fix the upload 500 (tractable) if you want another quick win first.
