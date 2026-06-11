# Margot Overnight Superpowers Execution Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Pull Margot into the Unite-Group command workflow and use superpowers-style subagent execution overnight to turn current Margot assets into a usable operator plan, working queue, and verification loop.

**Architecture:** Margot currently exists as a voice + retrieval + CRM task creation surface inside the Unite-Group repo, backed by Linear operating tickets and Supabase/ElevenLabs integrations. The overnight plan should avoid unsafe production writes, use sandbox-first rules for any DB/schema work, and use Linear as the operating source of truth.

**Tech Stack:** Next.js App Router, React, Supabase, ElevenLabs ConvAI, Linear API, Vercel, Hermes subagents/superpowers workflow.

---

## 0. Current Margot Inventory

### Local repo assets found

Project root:
`/Users/phillmcgurk/Unite-Group`

GitHub repo:
`https://github.com/CleanExpo/Unite-Group.git`

Local Margot files:

- `src/components/command-center/voice/MargotVoicePanel.tsx`
  - Client-side panel for “Talk to Margot”.
  - Loads ElevenLabs ConvAI widget from `https://unpkg.com/@elevenlabs/convai-widget-embed`.
  - Calls `/api/pi-ceo/margot-voice/signed-url` to create a secure signed voice session.
  - Renders operator-safe failure copy through `failure-taxonomy`.

- `src/components/command-center/voice/failure-taxonomy.ts`
  - Maps 401, 403, 429, 503, 502, network, and unknown errors to safe operator instructions.
  - Explicitly points missing ElevenLabs env to Vercel env fix.

- `src/app/api/pi-ceo/margot-voice/signed-url/route.ts`
  - Admin-gated signed URL endpoint.
  - Requires `ELEVENLABS_API_KEY` and `ELEVENLABS_MARGOT_AGENT_ID`.
  - Calls ElevenLabs signed URL endpoint with `include_conversation_id=true`.
  - Fails closed on missing env and upstream errors.

- `src/app/api/pi-ceo/margot-voice/task/route.ts`
  - Bearer-token protected voice packet ingest endpoint.
  - Requires `UNITE_CRM_INGEST_TOKEN`, `UNITE_CRM_ORG_ID`, `UNITE_CRM_WORKSPACE_ID`, `NEXT_PUBLIC_SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`.
  - Writes `voice_command_sessions` and `tasks` rows.
  - Assigns non-approval tasks to `Margot`; approval-required tasks to `Phill approval`.

- `tests/integration/api/margot-voice-signed-url.test.ts`
  - Tests admin gate, missing env fail-closed behavior, and signed URL response without leaking API key.

- `tests/integration/api/margot-voice-task.test.ts`
  - Tests token rejection, voice session + CRM task creation, and approval-required blocked task behavior.

- `scripts/margot-semantic-search-wrapper.ts`
  - Margot-specific wrapper around `semanticSearch`.
  - Uses threshold `0.76`.
  - Provides `margot_semantic_search` tool definition for 2nd Brain retrieval.

### Linear context found

Primary active Margot ticket:

- `UNI-2054` — Maintain Margot Command Center and RestoreAssist Content Index
  - State: In Progress
  - Owner: Margot
  - Route: Unite-Group operating system + RestoreAssist content index
  - Project: Brand OS Production Board
  - Output paths from ticket:
    - `/Users/phill-mac/hermes-agent-enhancement-report/MARGOT-COMMAND-CENTER.md`
    - `/Users/phill-mac/hermes-agent-enhancement-report/restoreassist-content-packs/RESTOREASSIST-CONTENT-INDEX.md`
  - Governance:
    - Keep statuses current.
    - Record missing files and blocked decisions.
    - Keep parked Toby/Duncan work out of RestoreAssist / Brand OS workflow.

Queued Margot content work:

- `UNI-2053` — Create CCW product category copy
  - State: Todo
  - Owner: Margot
  - Route: Unite-Group / CCW CRM
  - Skills requested in Linear: `client-identity-lock`, `business-brand-voice`, `ai-seo-content-brief`
  - Blocker: first product category topic decision needed.
  - Governance: do not mix CCW with RestoreAssist/Synthex/DR-NRPG/CARSI contexts.

Completed retrieval / brain infrastructure relevant to Margot:

- `UNI-2045` — Epic: 2nd Brain 10x Wrapper + Agentic Retrieval
  - Key gaps identified: semantic search not queryable by agents, Plaud not feeding vectors, wiki sync manual, no unified retrieval rules.

- `UNI-2049` — Deploy semantic_search RPC + tool wrappers for agents
  - Deliverable noted in Linear: `deploy_semantic_search.py` and agent tool registration plan.

- `UNI-2052` — Create unified retrieval rules for Margot and Pi-CEO
  - Deliverable noted in Linear: `unified_retrieval_rules.md`.
  - Rules from Linear comment:
    1. semantic_search first
    2. file reads second
    3. search_files third
    4. Linear API fourth
    5. web search last
  - Confidence thresholds:
    - `>0.8`: use directly
    - `0.6–0.8`: verify
    - `<0.6`: fallback

Other relevant context:

- `UNI-2030` — Obsidian Source ingestion: Unite-Group / Pi-CEO / Margot pack
  - Included `2026-05-17 - hermes - margot-conversation-os-directive.md` and Pi orchestration docs.
  - Linear says ingestion completed and mapped to wiki targets.

- `UNI-2028` — Hermes v0.14 rollout x_search
  - Linear says x_search templates are ready to enable in Margot/Research profiles.

### Current blockers / unknowns

- Vercel project is not locally linked because no Vercel credentials were available in this session.
- Vercel site is live at `https://unite-group.vercel.app` and returned HTTP 200 earlier.
- Local `.vercel` project metadata is not present yet.
- The command-line terminal was denied during late dependency checks, so do not assume `node_modules` exists or that tests have been run in this checkout.
- UNI-2054 references Mac Mini paths under `/Users/phill-mac/...`; those files are not confirmed present on this MacBook checkout.

---

## 1. Overnight Operating Principles

1. Linear is the operating queue.
2. No production DB/schema changes without sandbox wizard.
3. For code tasks: TDD where feasible, then spec review, then quality review.
4. Use fresh subagents per task.
5. Keep Margot / RestoreAssist / Brand OS context separate from CCW unless explicitly working UNI-2053.
6. Do not commit secrets, local env, or Vercel/Linear tokens.
7. Every overnight lane must produce either:
   - a repo artifact,
   - a Linear comment/update,
   - a verified test/log result,
   - or a clear blocked decision note.

---

## 2. Recommended Overnight Lanes

### Lane A — Margot Command Center Recovery / Inventory

**Objective:** Find or reconstruct Margot’s command-center artifact from the current repo + Linear context.

**Primary Linear:** `UNI-2054`

**Expected output:**
`docs/margot/MARGOT-COMMAND-CENTER.md`

**Steps:**
1. Search only inside `/Users/phillmcgurk/Unite-Group` for existing Margot docs.
2. If Mac Mini source files are reachable later, copy their contents into local docs.
3. If not reachable, reconstruct a local command-center document from:
   - local Margot code inventory above,
   - Linear UNI-2054 / UNI-2053 / UNI-2049 / UNI-2052 context,
   - current repo README/CLAUDE constraints.
4. Add sections:
   - Active Margot surfaces
   - Linear operating queue
   - Retrieval rules
   - Voice path health checklist
   - Blockers / decisions needed
   - Overnight work lanes
5. Do not mix Toby/Duncan unless explicitly listed as parked/out-of-scope.

**Verification:**
- File exists.
- Contains links/IDs for UNI-2054 and UNI-2053.
- Clearly names blockers and next actions.

---

### Lane B — Voice Health + Test Readiness

**Objective:** Validate Margot voice endpoint behavior locally without requiring production credentials.

**Files:**
- `src/app/api/pi-ceo/margot-voice/signed-url/route.ts`
- `src/app/api/pi-ceo/margot-voice/task/route.ts`
- `tests/integration/api/margot-voice-signed-url.test.ts`
- `tests/integration/api/margot-voice-task.test.ts`
- `src/components/command-center/voice/failure-taxonomy.ts`

**Steps:**
1. Inspect existing tests and identify missing cases.
2. Add tests only if gaps are obvious and low risk:
   - rate limit 429 maps to failure taxonomy,
   - invalid JSON returns `invalid_json`,
   - invalid packet returns `invalid_packet`,
   - task insert failure returns `crm_task_insert_failed`,
   - ElevenLabs upstream non-OK returns `elevenlabs_signed_url_failed`.
3. Run focused tests if terminal is available:
   - `npm test -- --runInBand tests/integration/api/margot-voice-signed-url.test.ts tests/integration/api/margot-voice-task.test.ts`
4. If dependencies are missing, record exact install/test blocker instead of guessing.

**Verification:**
- Existing tests pass or blocker is recorded.
- Any new tests fail first, then pass after minimal implementation.

---

### Lane C — Retrieval Rules Integration

**Objective:** Make Margot’s semantic retrieval path explicit and discoverable in this repo.

**Primary Linear:** `UNI-2052`, `UNI-2049`, `UNI-2045`

**Files:**
- `scripts/margot-semantic-search-wrapper.ts`
- `scripts/pi-ceo-semantic-search-wrapper.ts`
- `CLAUDE.md`
- `docs/margot/retrieval-rules.md` (create if missing)

**Steps:**
1. Inspect wrappers and confirm whether the TypeScript imports actually resolve.
2. Create `docs/margot/retrieval-rules.md` summarizing:
   - semantic_search first,
   - file reads second,
   - search_files third,
   - Linear fourth,
   - web last,
   - confidence thresholds.
3. Add Margot-specific guidance:
   - research/synthesis uses `margot_semantic_search`,
   - verify mid-confidence results with file reads,
   - use Linear for active queue only,
   - never blend client contexts.
4. If safe, add a short pointer in `CLAUDE.md` to the doc.

**Verification:**
- Retrieval doc exists.
- It references Margot, Pi-CEO, and confidence thresholds.
- No secrets or environment-specific tokens are added.

---

### Lane D — Linear Queue Hygiene

**Objective:** Turn Margot’s current Linear work into a clean overnight board.

**Primary Issues:**
- `UNI-2054` active
- `UNI-2053` queued / decision needed

**Steps:**
1. Leave `UNI-2054` in progress.
2. Add or prepare a Linear comment summarizing:
   - local repo Margot inventory,
   - missing Mac Mini source path check,
   - planned overnight lanes,
   - blockers.
3. Keep `UNI-2053` blocked/queued until the first CCW product category topic is supplied.
4. If creating new Linear issues, create only surgical tickets:
   - “Document Margot retrieval rules in repo”
   - “Add missing Margot voice endpoint tests”
   - “Reconcile Mac Mini Margot command-center artifact into Unite-Group repo”

**Verification:**
- Linear comment or local comment draft exists.
- No unrelated project contexts mixed into Margot’s active workflow.

---

### Lane E — Vercel / Env Readiness

**Objective:** Prepare, but do not force, Vercel linking and env checks.

**Known current status:**
- `vercel.json` exists.
- Live site: `https://unite-group.vercel.app`.
- Local `.vercel` link missing due missing credentials.

**Steps when credentials are available:**
1. `npx vercel login` or provide `VERCEL_TOKEN`.
2. `npx vercel link`.
3. `npx vercel pull --yes --environment=development`.
4. Confirm env presence for:
   - `ELEVENLABS_API_KEY`
   - `ELEVENLABS_MARGOT_AGENT_ID`
   - `UNITE_CRM_INGEST_TOKEN`
   - `UNITE_CRM_ORG_ID`
   - `UNITE_CRM_WORKSPACE_ID`
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

**Verification:**
- `.vercel/project.json` exists.
- `.env.local` or Vercel env pull completed without exposing secrets.
- Missing envs recorded by name only, not value.

---

## 3. Superpowers Subagent Execution Plan

Use fresh subagents and two-stage review.

### Task 1: Build Margot command-center doc

**Objective:** Create the local operator doc from inventory.

**Files:**
- Create: `docs/margot/MARGOT-COMMAND-CENTER.md`

**Subagent brief:**
Use the inventory from this plan. Do not run network calls. Do not edit code. Create an operator-facing doc with current state, Linear queue, voice system health checklist, retrieval rules pointer, blockers, and overnight lanes.

**Spec review:**
- Includes UNI-2054 and UNI-2053.
- Includes local file inventory.
- Includes blockers.
- Does not mix Toby/Duncan as active work.

**Quality review:**
- Clear, concise, operational.
- No secrets.
- Easy to use at 2am.

---

### Task 2: Document Margot retrieval rules

**Objective:** Make retrieval rules explicit in repo.

**Files:**
- Create: `docs/margot/retrieval-rules.md`
- Optionally modify: `CLAUDE.md` with a one-line pointer only.

**Subagent brief:**
Write a concise retrieval policy based on UNI-2052. Include priority order and confidence thresholds. Keep it general enough for Margot and Pi-CEO, with Margot-specific notes.

**Spec review:**
- Contains five-tier order.
- Contains thresholds.
- Contains Linear-as-active-queue rule.

**Quality review:**
- No over-engineering.
- No secret/env assumptions.

---

### Task 3: Margot voice test gap analysis

**Objective:** Identify missing tests before changing code.

**Files:**
- Read: `tests/integration/api/margot-voice-signed-url.test.ts`
- Read: `tests/integration/api/margot-voice-task.test.ts`
- Read: relevant API routes.
- Output: `docs/margot/voice-test-gap-analysis.md`

**Subagent brief:**
Do not implement yet. Produce a gap analysis with exact tests to add, expected behavior, and risk. If terminal unavailable, do not run tests; just mark as blocked.

**Spec review:**
- Lists existing coverage.
- Lists missing coverage.
- Gives exact test names.

**Quality review:**
- Practical and limited to Margot voice.

---

### Task 4: Linear overnight update draft

**Objective:** Prepare a concise update for UNI-2054.

**Files:**
- Create: `docs/margot/linear-uni-2054-overnight-update.md`

**Subagent brief:**
Draft a Linear comment summarizing local repo inventory, active blockers, overnight lanes, and decisions needed. Do not post it unless explicitly approved.

**Spec review:**
- Has clear status / evidence / blockers / next action sections.

**Quality review:**
- Ready to paste into Linear.
- No secrets.

---

## 4. Proposed Work Order for Tonight

1. Task 1 — Margot Command Center doc.
2. Task 2 — Retrieval Rules doc.
3. Task 4 — Linear update draft.
4. Task 3 — Voice test gap analysis.
5. If terminal becomes available:
   - install dependencies only if needed and approved,
   - run focused Margot tests,
   - then decide whether to add tests.
6. If Vercel token/login becomes available:
   - link Vercel,
   - pull env names,
   - verify Margot voice env readiness without printing secrets.

---

## 5. Decisions Needed From Phill

1. Should I recover the Mac Mini source files for UNI-2054 from `/Users/phill-mac/hermes-agent-enhancement-report/...` over the Thunderbolt/Mac Mini path, or reconstruct locally first?
2. For `UNI-2053`, what is the first CCW product category topic?
3. Are we allowed to post the overnight update to Linear automatically, or should it remain as a local draft?
4. Can Vercel be linked tonight via login or token?
5. Should overnight agents be limited to docs/plans only, or can they add tests/code after spec review?

---

## 6. Abort / Escalation Rules

Abort and ask Phill before:

- Any production DB write or migration.
- Any Vercel env mutation.
- Any secret/token storage.
- Any cross-project context merge involving CCW, RestoreAssist, Synthex, DR-NRPG, CARSI, Toby, or Duncan.
- Any destructive git operation.

Escalate if:

- Mac Mini source path is unreachable.
- Vercel auth blocks env verification.
- Tests cannot run due missing deps or broken install.
- Linear API is unavailable.

---

## 7. Definition of Done for Overnight Prep

- Margot command-center doc exists locally.
- Retrieval rules doc exists locally.
- UNI-2054 update draft exists locally or has been posted with approval.
- Voice test gap analysis exists locally.
- All blockers are explicit and assigned to either Phill, Vercel auth, Mac Mini access, or follow-up implementation.
