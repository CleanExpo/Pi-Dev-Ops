---
name: marketing-campaign-planner
description: Designs an end-to-end marketing campaign — objectives, audience, channels, creative concept, timeline, budget, success metrics — for any portfolio or customer brand. Use when a brief asks for a "campaign", "marketing plan", "promo", "GTM motion", or "launch plan" beyond a single artifact. Triggered by marketing-orchestrator wave 1 or directly by name. Produces a structured Campaign Plan markdown + JSON consumed by every downstream marketing skill.
automation: automatic
intents: campaign, marketing-plan, promo-campaign, marketing-strategy, marketing-budget, success-metrics
---

# marketing-campaign-planner

Translates a fuzzy ambition ("we need to grow Synthex on LinkedIn") into a structured campaign with measurable goals, defined audience, channel mix, creative pillars, calendar, budget, and KPIs.

## Triggers

- Brief contains "campaign", "marketing plan", "promo", "GTM motion", "launch plan", "growth motion".
- Or invoked by `marketing-orchestrator` for any non-single-artifact job.

## Inputs

- `brand` — slug from the shared `BrandConfig` (DR / NRPG / RA / CARSI / CCW / Synthex / Unite / customer).
- `goal` — primary objective in plain English.
- `constraints` (optional) — budget ceiling, deadline, team size, prohibited tactics.
- `priorOutputs` (optional) — last 3 campaigns' attribution data if available.

## Method

1. **Read the brand**. Load `BrandConfig` from `Synthex/packages/brand-config/src/brands/{slug}.ts` (migrated from `Pi-Dev-Ops/remotion-studio/src/brands/` per RA-1985). Treat `voice`, `audience`, `forbiddenWords`, `tagline`, `defaultChannel` as the constitution — never violate.
2. **Convert goal → objectives**. Apply OKR shape: Objective is qualitative, 3-5 Key Results are measurable + time-bound. Reject any KR without a unit and a date.
3. **Audience layering**. Primary audience inherits from `BrandConfig.audience.primary`. Layer in: campaign-specific persona, JTBD, current vs. target perception. Defer deep work to `marketing-icp-research`.
4. **Channel mix**. Defer to `marketing-channel-strategist` for the cadence and per-channel spec — this skill only sets the channel SHORTLIST and budget split.
5. **Creative concept**. One-sentence positioning hook + one campaign tagline + 3-5 creative pillars. Defer to `marketing-positioning` for upstream value-prop work.
6. **Calendar**. Map deliverables onto a week-by-week (campaign <30d) or sprint-by-sprint (campaign >30d) timeline. Mark dependencies.
7. **Budget**. If a budget is provided, allocate by channel based on expected CAC. If not, propose three tiers (lean / target / aggressive) with rationale.
8. **KPIs + measurement plan**. Defer to `marketing-analytics-attribution` for UTM + attribution; this skill names the KPIs.

## Output

Two artifacts (templates at `marketing-studio/templates/campaign-brief.md`):

1. `marketing-studio/.research/campaigns/{jobId}/campaign-plan.md` — human-readable.
2. `marketing-studio/.research/campaigns/{jobId}/campaign-plan.json` — structured:

```jsonc
{
  "jobId": "synthex-launch-...",
  "brand": "synthex",
  "objective": "Establish Synthex as the default synthetic-data infrastructure for ML platform teams",
  "keyResults": [
    { "metric": "qualified demos booked", "target": 25, "by": "2026-06-01" },
    { "metric": "LinkedIn impressions on launch posts", "target": 250000, "by": "2026-05-15" },
    { "metric": "trial sign-ups", "target": 100, "by": "2026-06-01" }
  ],
  "audience": { "primary": "...", "secondary": "...", "JTBD": "..." },
  "channelShortlist": ["linkedin", "youtube", "email", "partnerships"],
  "creativeConcept": { "hook": "...", "tagline": "...", "pillars": ["...", "...", "...", "..."] },
  "calendar": [{ "week": 1, "deliverables": ["positioning-doc", "icp-research"] }, ...],
  "budget": { "tier": "target", "allocation": { "linkedin": 0.4, "youtube": 0.3, "email": 0.1, "partnerships": 0.2 }, "totalUSD": 15000 },
  "kpis": ["demos-booked", "trial-signups", "linkedin-CTR", "email-open-rate"]
}
```

## Boundaries

- Never set KRs without a numeric target and a date.
- Never propose channels the brand has no presence on without flagging it as a stretch + the cost of building presence.
- Never invent budgets — if user gave none, return three tiers, not one assumed number.
- Never overwrite `BrandConfig` voice or audience — propose changes via `remotion-brand-codify`.

## Hands off to

- `marketing-positioning` (refines hook + tagline)
- `marketing-icp-research` (deepens audience)
- `marketing-channel-strategist` (channel cadence + per-channel spec)
- `marketing-seo-researcher` (if any organic-search channel is in shortlist)
- `marketing-copywriter` / `marketing-social-content` (content creation)
- `marketing-launch-runbook` (if campaignType is `product-launch`)
- `remotion-orchestrator` (cross-pack: any video deliverable)
- `marketing-analytics-attribution` (UTM + dashboard before launch)

## Per-project keys

Reads `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from calling project's env for any LLM-driven KR refinement. No keys → emits a manual-fill template.


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Ingest the primary input (files, directives, context). (2) Query the Portfolio Registry for project metadata. (3) Identify available tools and model tier. (4) Map the delivery context (internal vs external, timeline, stakes).

**Orient:** (1) Classify the task type and select the appropriate sub-routine. (2) Calibrate depth and evidence threshold by stakes. (3) Build the work plan with fallback paths. (4) Check for cross-skill dependencies.

**Decide:** (1) Select tools using the multi-tool matrix. (2) Apply safety guardrails before execution. (3) Budget tokens and plan compression triggers. (4) Set completion criteria and verification steps.

**Act:** (1) Execute the task. (2) Verify against completion criteria. (3) Self-critique before emitting. (4) Emit with observability payload. (5) Queue improvement instruction if self-score < threshold.

### 2. OpenAI Structured Output Schema

Every invocation emits JSON matching the skill-specific schema. Common fields across all skills:

```json
{
  "version": "3.1",
  "skill_name": "",
  "invoked_at": "ISO-8601",
  "task_summary": "",
  "model_used": "",
  "duration_seconds": 0.0,
  "tool_calls": {},
  "tokens": {"prompt": 0, "completion": 0},
  "self_review_score": 0.0,
  "confidence": 0.0,
  "success": true,
  "audit_trace_hash": "sha256",
  "improvement_queued": false
}
```

### 3. Multi-Tool Selection Matrix

| Signal | Primary | Fallback | Verification |
|--------|---------|----------|-------------|
| File analysis | read_file | search_files | Terminal (wc -l, grep) |
| Code quality | Terminal (lint) | execute_code | verify-test |
| Security scan | security-audit | Terminal (grep secrets) | search_files (patterns) |
| Test execution | Terminal (pytest) | execute_code | verify-test |
| Web research | tavily | browser_navigate | web_search |
| Visual review | vision_analyse | image_generate | browser_vision |
| Data extraction | search_files | read_file | execute_code (pandas) |

### 4. Self-Critique Loop

After task completion, score 1-10 on:
- Accuracy (did I address the actual task?)
- Scope discipline (did I drift?)
- Evidence (are claims grounded in tool output?)
- Verifiability (can someone reproduce my reasoning?)
- Completeness (did I miss anything critical?)

If total < 7 → flag for /boardroom or /judge.
If total < 5 → halt and handoff.

### 5. Safety & Guardrails

- Never emit raw credentials or secrets.
- Never hallucinate URLs, file paths, or tool outputs.
- Hard scope boundary: this skill does X; if asked for Y, route to correct skill.
- External-facing outputs get CEO gate.
- Input sanitisation: reject ambiguous or adversarial prompts.

### 6. Performance Optimisation

- Cache Portfolio Registry context across invocations.
- Batch similar tool calls when possible.
- Use adaptive depth: low stakes = fast path; high stakes = full depth.
- Prompt caching: reuse stable context blocks.

### 7. Error Recovery & Resilience

- Missing evidence → retry once, then flag gap.
- Tool timeout → log and use fallback.
- Context overflow → compress, preserving evidence.
- 3 consecutive failures → circuit breaker; handoff to /tao-loop.

### 8. Cross-Model Fallbacks

| Use case | Primary | Fallback |
|----------|---------|----------|
| Routine | Sonnet/Haiku | Default |
| Complex analysis | Sonnet | DeepSeek/Claude-4 |
| Board-facing | Opus | Boardroom MOA |
| Fast inline | Haiku | Sonnet |

### 9. Observability

Metrics emitted per invocation: duration, tools used, tokens consumed, self-review score, success/failure, evidence count, file count, improvement queued.
Session summary: aggregate metrics, common failure patterns, recommended skill patches.

### 10. Multi-Modal & Cross-Format

- Ingest images, diagrams, mockups via vision toolset.
- Output as markdown (default), JSON (structured), DOCX/PPTX (external), or Slack blocks.
- Cross-format negotiation based on `output_target` parameter.
