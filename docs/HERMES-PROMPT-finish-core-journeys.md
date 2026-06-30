# Hermes instruction — build + prove the remaining core journeys (the "finalise" run)

Note: computer_use (desktop clicking) is the wrong tool for this — it can't build a drip API
or fix a 500. The right "finalise" is this autonomous build-and-prove run, the same engine
that got Contact CRUD to a real verified PASS. It is a BUILD run (bigger/riskier than
verification); drip + transcription are net-new, so expect real verified progress + an honest
report, not a guaranteed 100% in one pass.

---

```
MISSION (Unite-Hub): Drive the core journeys from their current verified state to PASS by BUILDING the
missing/broken pieces and PROVING each end-to-end. Autonomous, one run; do NOT wait between items; if one
is blocked, log it and move on. One PR: feat/finish-core-journeys. Never push to main.

CURRENT TRUTH (from COVERAGE.md — do not re-litigate):
- PASS: Contact CRUD + RLS, Integrations status, auth/health/protected-route safety.
- FAIL: Drip campaign — no api/campaigns/drip lifecycle exists. BUILD it.
- BROKEN/MISSING: authenticated upload returns 500 (ANTHROPIC_API_KEY path); transcription endpoint missing.
- UNKNOWN: Lead scoring (library logic exists, no API route); Gmail OAuth import (human consent).

KEY SOURCING: get SUPABASE_SERVICE_ROLE_KEY from `supabase projects api-keys --project-ref
lksfwktwtmyznckodsau --output json` (in-memory only; NOT vercel env run). Never print/commit secrets.

SAFETY ENVELOPE: scoped reversible prod TEST data only (tagged throwaway users/workspaces/contacts/
campaigns/uploads), full verified cleanup. No destructive schema ops, no deploys, no real emails, no billing.
One change at a time; after each, re-run that item's check AND re-run the existing PASS guards
(contact-crud, core-journeys) so you never regress them.

HONESTY CONTRACT: PASS only with re-run evidence (status+body / test output). No "done/tick" without proof.
Unverifiable or human-gated -> UNKNOWN. Update COVERAGE.md honestly.

WORK (priority order — build minimal-correct, then PROVE, then leave an e2e guard):
1. DRIP CAMPAIGN: implement create -> add step -> enroll -> process per the documented contract. Prove with a
   tagged test campaign + test contact; processing must NOT send to any real address (test domain/dry-run only).
   If the full lifecycle can't be safely completed this run, build+prove as far as possible, mark remainder UNKNOWN.
2. UPLOAD 500 + TRANSCRIPTION: diagnose+fix the authenticated upload 500; implement a transcription endpoint
   (smallest viable). Prove upload+transcription with a tiny tagged file. If the transcription provider/cost blocks
   live execution, prove the wiring with a mocked provider and mark the live step UNKNOWN.
3. LEAD SCORING API: wire authenticated seed-contact -> run scoring -> persist score over the existing library.
   Prove with a tagged contact + known signals; assert the score matches the rule.
4. GMAIL: verify everything except consent; write the exact human OAuth-consent steps to DECISIONS_NEEDED.md.
   Do not fake import.

GUARDRAILS: never break existing PASS journeys (re-run their guards each cycle). Detect stasis; respect a cost
ceiling. Teardown all test data and verify removal.

OUTPUT (one PR): updated COVERAGE.md (each journey PASS/FAIL/UNKNOWN + overall %), STATUS.md (what now PASSES,
what's left, exact human steps), EVIDENCE.md, DECISIONS_NEEDED.md, e2e guards, small proven commits.

PRINCIPLE: build the minimum correct thing, prove it as a real user with tagged throwaway data, clean up, or
mark UNKNOWN. Move through ALL items; the run ends when each has been built+proven or honestly blocked.
```

---

Judge it by COVERAGE.md: the PASS count should rise from 2 toward 5. Anything still FAIL/UNKNOWN is
either honestly unfinished or human-gated (Gmail consent), with the exact next step in DECISIONS_NEEDED.md.
Re-run one newly-PASS e2e guard yourself before believing it.
```
