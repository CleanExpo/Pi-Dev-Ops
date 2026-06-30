# Hermes instruction — next targeted build: Transcription endpoint

Upload persistence (ai_file_cache, PR #103) is the prerequisite and now PASSES, so transcription's
foundation exists. Keep it narrow: build the endpoint, prove the wiring with a MOCKED provider (no
live cost/credentials needed), and mark the live-provider step UNKNOWN if blocked. Do not invent
schema; use only an existing additive migration or flag it.

---

```
MISSION (Unite-Hub): Build the transcription endpoint and PROVE its wiring end-to-end with a MOCKED provider.
ONE target. Branch: feat/transcription-endpoint. One PR. Never push to main. Never deploy.

CURRENT TRUTH: persisted file upload now PASSES (ai_file_cache exists, PR #103). No transcription endpoint
exists yet. Build the smallest viable one that takes an uploaded file and produces/persists a transcript.

KEY SOURCING: SUPABASE_SERVICE_ROLE_KEY from `supabase projects api-keys --project-ref
lksfwktwtmyznckodsau --output json` (in-memory only; NOT vercel env run). Never print/commit secrets.

SAFETY ENVELOPE: scoped reversible prod TEST data only (tagged throwaway), full verified cleanup. No deploys,
no real emails, no billing. SCHEMA: if persistence needs a new table/column, apply ONLY an existing in-repo
ADDITIVE migration (CREATE ... IF NOT EXISTS, no alter/drop). If no such migration exists, build the endpoint to
return the transcript, mark persistence UNKNOWN, and write the needed migration to DECISIONS_NEEDED.md — do NOT
invent ad-hoc DDL. One change at a time.

HONESTY CONTRACT: PASS only with re-run evidence (HTTP status+body / test output). No "done/tick" without proof.
Live-provider or human-gated steps -> UNKNOWN with the reason. Update COVERAGE.md honestly.

PLAN
1. Implement the transcription endpoint (repo convention) over the existing upload/ai_file_cache infra. Use the
   documented provider (e.g. Whisper/OpenAI) behind an interface you can MOCK in tests.
2. PROVE WIRING with a MOCKED provider: provision a tagged test user/workspace; upload a tiny tagged file;
   trigger transcription; assert the endpoint returns/persists the (mock) transcript, scoped to the authed user.
   Record status+body. This proves the journey without paying for or needing live provider credentials.
3. LIVE PROVIDER: if real provider credentials/cost are available and within the safety envelope, run ONE tiny
   live sample and record it; otherwise mark the live-provider step UNKNOWN and write the exact human step
   (provider API key / cost approval) to DECISIONS_NEEDED.md. Do NOT fake a live transcript.
4. TEARDOWN test data (not schema); verify removed. Leave a self-cleaning e2e guard.
5. Update COVERAGE.md: transcription = PASS (mocked wiring) with evidence; live step PASS or UNKNOWN. Open the PR.

REGRESSION: re-run existing PASS guards (contact-crud, integrations, lead-scoring, file-upload) before finishing;
never regress a PASS.
PRINCIPLE: prove the wiring for a real authed user with a mocked provider and tagged data, clean up, or mark
UNKNOWN. One journey only.
```

---

After this: COVERAGE.md should show transcription = PASS (mocked wiring), with the live provider either PASS
or an honest UNKNOWN + the exact key/cost step in DECISIONS_NEEDED.md. Then Drip campaign is the last big
net-new build, and Gmail/Outlook OAuth is the human-consent step.
