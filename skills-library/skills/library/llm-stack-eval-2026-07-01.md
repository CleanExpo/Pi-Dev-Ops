# SPM Spec — Do the 9 "LLM-stack" repos fit the 2nd Brain (Pi)?

**Date:** 2026-07-01 · **Mode:** read-only evaluation · **Author:** Pi-Dev-Ops SPM
**Repos:** DSPy · crawl4AI · chonkie · marker · langfuse · qdrant · outlines · litellm · instructor
**Evidence:** 6 first-source repo briefs + 2 read-only Pi architecture/ingestion surveys (this session's sub-agents). outlines/litellm/instructor first-source briefs still landing — those three flagged `[brief pending]`.

---

## 1. Task
Decide, per repo and for the combined stack, whether each of the 9 GitHub projects should be **adopted / partially adopted / deferred / rejected / escalated** for the Pi-CEO "2nd Brain" system, with a build-ready plan for the parts that pass.

## 2. Current project context
- **Pi-Dev-Ops backend = Python 3.11** (`pyproject.toml requires-python >=3.11`, `anthropic 0.97.0`, FastAPI, `uv`). Python libs can run in-process **here only**.
- **Nexus (`unite-group`) and Fable-Prompt-Engineer = TypeScript/Next.js** — none of these Python libs run in-process there.
- **No RAG/vector pipeline exists.** Storage = Markdown-in-vault (`~/2nd Brain/Sources/*.md`) + Supabase rows; retrieval = **grep/FTS + OKF index reads, not semantic**. Only `pgvector` ref is `supabase/migration.sql:255 build_episodes.embedding` and it's dormant (`session_recorder.py:164` "No pgvector on Railway").
- **Prompts are all hand-written strings** (`board_meeting.py:46`, `tao_judge.py:_build_prompt`, `coaches/prompts/*.ts`); **no optimization layer anywhere** (`dspy` grep-clean).
- **Model routing already exists:** `model_policy.select_model` (Opus-only-for-planner, violation JSONL) + `swarm/model_router.py` (Anthropic→OpenRouter→Ollama) + Hermes/OpenRouter gateway. **LiteLLM is already a transitive dep** of DSPy/crawl4AI/chonkie.
- **Observability today:** Vercel-native + `supabase_log.py` + `.harness/agent-sdk-metrics/*.jsonl`. **Locked constraint `feedback-no-sentry`: no third-party observability platform — Vercel built-in only (stated 11+ times).**
- **Always-on path = Railway + Vercel + GitHub Actions only.** Headless Chromium / heavy stateful services don't belong on the Railway backend.
- **Anthropic Max is the mandated workhorse** (`feedback-anthropic-first`).

## 3. Problem statement
The 9 repos assemble a canonical **RAG + LLMOps platform**: ingest → chunk → embed/store/retrieve → generate-with-structure → optimize → route → observe. Pi today has **none** of that spine — it retrieves by grep/OKF and prompts by hand. The real question is not "are these good tools" (they are) but **"which problems does Pi actually have today,"** because most of this stack solves problems Pi hasn't hit yet.

## 4. Desired outcome
A high-value, low-regret subset adopted with bounded scope; the speculative/heavy/constraint-violating pieces explicitly deferred or escalated — no wholesale platform build.

## 5. Scope / non-goals
- **In scope:** per-repo fit verdict; a minimal build plan for the passing subset; explicit "do not build" list.
- **Non-goals:** building a full RAG platform; adding a vector DB; deploying a self-hosted observability stack; touching `model_policy` routing authority; any change to the TS Nexus.

## 6. Existing capability review (do NOT rebuild)
- **FABLE playbook distiller** already mines `~/.claude/projects` JSONL into behaviour metrics → `FABLE_PLAYBOOK.md`. DSPy must **consume** this corpus, not replace it.
- **`tao_judge`** already returns a scalar score [0,1] — that IS the metric a DSPy optimizer needs.
- **`model_policy` + `swarm/model_router` + Hermes** already do provider routing/fallback — LiteLLM proxy would duplicate them.
- **source-ingest tiers** (margot deep_research → WebSearch → WebFetch → browser-harness → Bright Data) already own research-synthesis, SERP (DataForSEO), authed/anti-bot pages.
- **Vercel-native observability** already owns prod telemetry (locked, no-Sentry).

## 7. Specialist board (condensed)
- **Architect:** the only in-process home is Python Pi-Dev-Ops; anything web/browser-based must run **local/launchd**, not Railway. A vector DB is a new stateful service against always-on-minimalism.
- **Security/Legal:** **marker** = GPL-3.0 code + OpenRAIL-M weights **free only under $2M revenue/funding** — a landmine for a commercial/$2B-ambition org. **langfuse/qdrant** self-host add attack surface + ops.
- **Cost:** DSPy "compile" = many LM calls (must stay off Opus, respect `TAO_MAX_COST_USD`). marker wants a GPU. langfuse self-host = 4 stateful services (PG+ClickHouse+Redis+S3).
- **Product:** current retrieval (grep/OKF over 33–385 md files) works at current scale; semantic RAG is not yet a felt pain.
- **Devil's advocate:** adopting the stack because it's "the modern LLM stack" is cargo-culting; adopt only where a *current* Pi pain maps to a repo.

## 8. Judge challenge — scores
- **Wholesale 9-repo adoption: 55/100 → REDUCE SCOPE.** Solves speculative future problems; adds heavy infra vs locked constraints; ~half conflicts with existing capability or locked memory.
- **Reduced experiment (instructor + crawl4AI-Tier3.5 + one DSPy proof): 82/100 → APPROVE EXPERIMENT.**

## 9. Proposed solution — per-repo verdicts

| Repo | Layer | Verdict | Why (one line) |
|---|---|---|---|
| **instructor** | structured output | **ADOPT (narrow)** `[brief pending]` | Works with the Anthropic API via tool-use+Pydantic-retry (no logits); formalizes Pi's existing "JSON-only + parse-retry" discipline. MIT, pure-Python. |
| **crawl4AI** | web ingest | **PARTIAL ADOPT** | Fills a real gap — unattended headless-JS fetch + deep-crawl + clean Markdown as **Tier 3.5** in source-ingest, run **local/launchd** (not Railway). Apache-2.0. Must not touch margot/DataForSEO/browser-harness/Bright-Data turf. |
| **DSPy** | prompt optimize | **APPROVE EXPERIMENT (gated)** | One proof on the `feedback_loop` classifier (closed labels) using `tao_judge` as metric; measure lift before more. Alpha; needs a trainset+metric harness that doesn't exist yet; keep compile off Opus. |
| **chonkie** | chunk | **DEFER (adopt only inside a RAG build)** | Best-in-class light chunker (MIT, 49 MB) — but only useful once a retrieval/embedding pipeline exists, which it doesn't. No standalone justification today. |
| **litellm** | routing | **PARTIAL (SDK only, no proxy)** `[brief pending]` | Already a transitive dep of DSPy/crawl4AI/chonkie — accept it there. Do **not** deploy the LiteLLM proxy: it duplicates `model_policy` + `model_router` + Hermes/OpenRouter. `model_policy` stays the authority. |
| **marker** | doc ingest | **DEFER / prefer Docling** | Real PDF→Markdown gap, but GPL-3.0 + OpenRAIL-M weights **free only <$2M revenue** = commercial landmine; GPU-preferred. Use **Docling (MIT)** as the default for anything client-facing; marker only for internal <$2M personal-use ingestion. |
| **qdrant** | vector DB | **DEFER (use pgvector first)** | No RAG exists; when it does, Supabase **pgvector** (already in-stack) is the low-regret first move. Qdrant only earns a second stateful service at multi-million-vector scale. Apache-2.0. |
| **outlines** | constrained gen | **REJECT (for the Claude stack)** `[brief pending]` | Guaranteed-structure works by masking **logits** → local/open-weight models only. The Anthropic API exposes no logits, so its core value doesn't apply to the mandated workhorse. Revisit only for a local-model (Ollama) tier. |
| **langfuse** | observe/eval | **ESCALATE to Board** | Genuine gap (no LLM-native tracing/eval/prompt-mgmt) but self-host = 4 stateful services and it **directly contradicts locked `feedback-no-sentry`** (Vercel-native only). Board call: reject prod self-host; the eval-dataset feature (Cloud free tier, no prod traces) is the only piece worth a scoped trial alongside the DSPy experiment. |

**Combined-pipeline finding:** the 9 form a full RAG+LLMOps platform Pi does not currently have or need at its scale. Adopt the two that map to a *current* pain (structured output; unattended ingest); treat the RAG spine (chunk/vector/embed) as a single future project gated on a real retrieval pain, not nine independent adoptions.

## 10. UX requirements
No end-user UI. Developer-facing: `instructor` wraps the existing Anthropic client (drop-in); crawl4AI is a local CLI/module invoked by source-ingest writing into the existing `Sources/*.md` + `SOURCE-LIBRARY.md` convention (no new storage surface).

## 11. Technical requirements
- Route every LM call through `model_policy.select_model()`/`resolve_to_id()`; never `model="claude-opus-*"`; honour `TAO_USE_AGENT_SDK=1`.
- crawl4AI/marker run under **launchd on the Mac**, never the Railway always-on service (headless Chromium / GPU).
- DSPy compile capped by `TAO_MAX_COST_USD`; optimizer LM calls on Sonnet/Haiku (evaluator role), never Opus.
- instructor validates with Pydantic + bounded retries (cap re-asks — each failure = extra LM call).

## 12. Security / privacy
- **marker license gate is decision-critical** — do not ship marker in any >$2M-revenue/commercial path; Docling (MIT) is the safe default.
- No new secrets to third-party SaaS; langfuse Cloud (if Board approves the eval-only trial) must not receive prod traces (keeps `feedback-no-sentry` intact for production).
- crawl4AI honours robots/ToS; escalate anti-bot pages to Bright Data, not stealth.

## 13. Verification plan
- **instructor:** unit test that `tao_judge`/`feedback_loop` return a valid Pydantic object on malformed model output after ≤N retries; compare parse-failure rate vs the current hand-parse.
- **crawl4AI:** ingest a JS-heavy page unattended → clean Markdown lands in `Sources/`, matches a golden snapshot; confirms the Tier-3.5 gap is filled without a live Chrome session.
- **DSPy:** hold-out set of labelled `lessons.jsonl` classifications; measure accuracy lift of an optimized prompt vs the current static `_PATTERN_PROMPT`; **ship only if lift ≥ a set threshold at acceptable cost.**

## 14. Loop / stress testing
- crawl4AI deep-crawl bounded (max pages/depth, cache on) to avoid runaway cost/bans.
- DSPy compile under `LoopCounter` + cost ceiling; abort on `TAO_HARD_STOP`.

## 15. Acceptance criteria
1. `instructor` integrated into one JSON-producing path with a passing retry/validation test and a measured parse-failure-rate drop.
2. `crawl4AI` Tier-3.5 script ingests an unattended JS page to `Sources/` with a golden-snapshot test, running under launchd (not Railway).
3. A DSPy proof-of-value report on `feedback_loop` with a go/no-go number.
4. A one-paragraph Board memo on langfuse (eval-only Cloud trial vs reject) and a written "defer" record for chonkie/qdrant/marker/outlines with the trigger that would revisit each.

## 16. Goal command
`/goal Integrate instructor into tao_judge + feedback_loop (Pydantic response_model + bounded retries, routed via model_policy), add a crawl4AI Tier-3.5 launchd ingest script writing to Sources/, and run a DSPy proof-of-value on the feedback_loop classifier using tao_judge as the metric — each with the tests in §13; ship only the ones that pass their acceptance number.`

## 17. Implementation sequence
1. **instructor** into `feedback_loop` (smallest, closed-label) → then `tao_judge`. (lowest risk, immediate reliability win)
2. **crawl4AI** Tier-3.5 local ingest script + golden test.
3. **DSPy** proof-of-value on `feedback_loop` (needs the metric harness built first).
4. **Board memo** on langfuse; **defer records** for chonkie/qdrant/marker/outlines.

## 18. Session-handoff seed
Backend Python 3.11 = only in-process home; Nexus is TS. No RAG today (grep/OKF). `tao_judge` scalar = DSPy metric. LiteLLM already transitive (SDK yes, proxy no). marker license <$2M gate → prefer Docling. outlines needs logits → not Claude. langfuse violates `feedback-no-sentry` → Board. Adopt instructor + crawl4AI-Tier3.5; experiment DSPy; defer the RAG spine until a real retrieval pain.

## 19. Final recommendation
**REDUCE SCOPE + APPROVE EXPERIMENT.** Reject wholesale adoption. **Adopt now:** `instructor` (reliability of existing JSON paths) and `crawl4AI` (Tier-3.5 unattended ingest, local). **Experiment:** `DSPy` on one prompt with a go/no-go metric. **Defer with a named trigger:** `chonkie`, `qdrant`, `marker`(prefer Docling) until a real RAG/document pain exists. **Reject:** `outlines` (logit-only, not Claude). **Escalate:** `langfuse` (gap vs locked no-Sentry constraint → Board). Keep `model_policy` as routing authority; accept `litellm` only as the transitive SDK dep, never its proxy.
