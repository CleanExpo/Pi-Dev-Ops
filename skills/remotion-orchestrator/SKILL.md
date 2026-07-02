---
name: remotion-orchestrator
description: /remotion-video one-shot Remotion command skill and ENTRY POINT for the Remotion Skills Package. Use for video, explainer, ad, promo, reel, intro, social cut, marketing, training, or launch videos. Reads the brief, classifies intent, enforces one single Synthex ElevenLabs voice, emits a production/wave plan, and dispatches the right sub-skills in topological order. Always invoked first.
automation: automatic
intents: video, explainer, ad, promo, reel, intro, social, render, marketing-video, training-video, 60s, 30s, 15s, remotion, remotion-skills-package
---

# remotion-orchestrator — Remotion Skills Package entry point

## /remotion-video one-shot command

`/remotion-video` is the one-shot command lane for Remotion marketing videos. It turns a rough brief into one governed production packet, one render path, and one final evidence report.

Hard rules for this command path:

- single voice only; no multi-voice casts and no per-scene voice switching.
- use existing Synthex ElevenLabs credentials and voice configuration only.
- no new vendors, no new accounts, no connector platforms.
- start with dry-run unless the operator explicitly asks for production render.
- write `.harness/remotion/<jobId>/production-packet.json`, `script.md`, `preflight-report.md`, and `render-command.sh`.
- never commit generated MP4s.

The command routes through `remotion-script`, `remotion-production`, `remotion-direction`, `remotion-editing`, `remotion-integrations`, and `remotion-professionalism`, while preserving the existing Remotion Skills Package workflow below.

Single entry point for the Remotion Skills Package — a set of 10 sibling skills (`remotion-orchestrator`, `remotion-brand-research`, `remotion-brand-codify`, `remotion-designer`, `remotion-colour-family`, `remotion-motion-language`, `remotion-screen-storyteller`, `remotion-marketing-strategist`, `remotion-composition-builder`, `remotion-render-pipeline`) installed globally at `~/.claude/skills/remotion-*` (symlinked to `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/skills/remotion-*`). Available in every project, not just Pi-Dev-Ops.

## Discovery brief gate (turn 1, mandatory)

Adopted from `nexu-io/open-design` (Apache-2.0). Before any wave plan is emitted, lock the brief. Refuse to proceed until every required field is filled — vague briefs produce overlong wave plans and off-brand renders.

### Required fields

| Field | Type | Notes |
|---|---|---|
| `brand` | `BrandSlug` | Must resolve in `src/brands/`. Unknown → dispatch `remotion-brand-research` first. |
| `composition` | `Explainer` \| `Intro` \| `SocialAd` \| `NIRReport` \| `ProductDemo` | v1 supports `Explainer`; others fall back with note. |
| `channel` | `linkedin` \| `youtube` \| `instagram` \| `tiktok` \| `training` | Drives aspect ratio + duration discipline. |
| `aspectRatio` | `1920x1080` \| `1080x1920` \| `1080x1080` | Defaults from `channel` if omitted. |
| `durationSec` | 15 \| 30 \| 60 \| 90 \| 120 | Drives wave-count cap. |
| `topic` | string | One sentence on what the video says. "Brand awareness video" alone is rejected — must name the specific point. |
| `audience` | string | Inherited from `BrandConfig.audience.primary` if omitted, but founder must confirm. |

Optional: `school` (visual-school override for the colour generator), `voiceoverScript` (skip storyteller if pre-written), `referenceComposition` (existing job to remix).

### Hard stop conditions

- `topic` reads as a category ("our product", "the launch") rather than a specific claim → block.
- `composition` ≠ `Explainer` in v1 without explicit fallback acknowledgement → block.
- Multiple brands named in one brief → split into N parallel jobs (one per brand); never blend.

The gate runs *before* the wave plan is computed. A blocked brief never reaches the dispatcher.

## Invocation

The user can invoke the package by:
- Saying any of: **"use the Remotion Skills Package"**, **"remotion package"**, **"use remotion"**.
- Naming any individual skill (e.g. "use remotion-designer to QA this layout").
- Submitting a brief that classifies as `intent: "video"` via [`Pi-Dev-Ops/app/server/brief.py`](/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/brief.py).

Translates a free-text brief into a structured render job and a wave plan that the Pi-Dev-Ops orchestrator ([`app/server/orchestrator.py`](/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/orchestrator.py)) dispatches via P3-B fan-out.

## The Remotion project

All compositions, brand configs, motion / colour helpers, and the render entry live at:

```
/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/remotion-studio/
```

When working from any other project, sub-skills `cd` into that path before reading or editing brand / composition files. The render entry is `npx tsx render/render.ts ...` from inside `remotion-studio`.

## Triggers

Brief contains any of: `video`, `explainer`, `promo`, `ad`, `reel`, `intro`, `outro`, `cta`, `social cut`, `60s`/`30s`/`15s`, `render`, `marketing video`, `training video`, `release video`, `feature video`, paired with one of the brand identifiers `dr` / `disaster recovery` / `nrpg` / `ra` / `restoreassist` / `carsi` / `ccw` / `carpet cleaners warehouse`.

## Inputs

The Pi-Dev-Ops planner (Opus 4.7) calls this skill with:
- `brief` — original free-text request
- `repo_url` — usually `local:Pi-Dev-Ops/remotion-studio`
- `linear_team_id`, `linear_project_id` — pre-resolved from `.harness/projects.json`

## Output

A wave plan JSON written to `remotion-studio/.research/wave-plans/{job_id}.json` with this shape:

```jsonc
{
  "jobId": "ra-nir-explainer-2026-04-28T15-30-00",
  "brand": "ra",
  "composition": "Explainer",
  "channel": "linkedin",
  "durationSec": 60,
  "topic": "RestoreAssist NIR Phase 1 standardisation",
  "linear": { "teamId": "...", "projectId": "..." },
  "outputPath": "output/ra-nir-explainer-2026-04-28T15-30-00.mp4",
  "waves": [
    { "id": 1, "parallel": [ {"skill":"remotion-brand-research","if":"brands/ra.ts missing or stale"}, {"skill":"remotion-marketing-strategist"} ] },
    { "id": 2, "parallel": [ {"skill":"remotion-screen-storyteller"}, {"skill":"remotion-colour-family","if":"palette incomplete"}, {"skill":"remotion-motion-language","if":"motion missing"} ] },
    { "id": 3, "parallel": [ {"skill":"remotion-brand-codify","if":"any new brand artifacts"}, {"skill":"remotion-designer"} ] },
    { "id": 4, "serial":   [ {"skill":"remotion-composition-builder"}, {"skill":"remotion-render-pipeline"} ] }
  ]
}
```

## Wave-count discipline

- ≤3 waves for output <30s
- ≤5 waves for output ≤120s
- ≤8 waves for output >120s

Over-decomposition is the failure mode this guards against.

## Composition routing (brief → composition id)

| Brief signal | composition |
|---|---|
| "explainer", "feature video", "how it works" | `Explainer` |
| "intro", "title card", "channel opener" | `Intro` (v1.1) |
| "ad", "promo", "reel", "social cut", "Instagram", "TikTok" | `SocialAd` (v1.1) |
| "NIR report", "inspection report", RA + "report" | `NIRReport` (v1.1) |
| "demo", "product walkthrough" | `ProductDemo` (v1.1) |

v1 supports `Explainer` only. Other composition ids return: "{Composition} ships in v1.1 — falling back to Explainer with channel-specific framing".

## Brand resolution

Match keywords → BrandSlug:
- `disaster recovery`, `dr` → `dr`
- `nrpg` → `nrpg`
- `restoreassist`, `ra`, `nir` → `ra`
- `carsi` → `carsi`
- `ccw`, `carpet cleaners warehouse` → `ccw`

If brief names multiple brands, ask the planner to split into N parallel jobs (one per brand) and emit N wave plans. Never blend brands into one composition.

## Linear routing

After the render skill writes the MP4, this skill (or the render skill) opens a Linear ticket in the project mapped from `.harness/projects.json`:

| Brand | Linear team | project |
|---|---|---|
| ra | `a8a52f07-63cf-4ece-9ad2-3e3bd3c15673` (RA) | `3c78358a-b558-4029-b47d-367a65beea7b` |
| dr / nrpg | `43811130-ac12-47d3-9433-330320a76205` (DR) | `d2c1d63b-1e85-424d-9278-efff15b0d46b` |
| carsi | `91b3cd04-...` (GP) | resolved at runtime |
| ccw | runtime | runtime |

## What this skill does NOT do

- Does not author compositions — that's `remotion-composition-builder`.
- Does not run `npx remotion render` — that's `remotion-render-pipeline`.
- Does not edit BrandConfig files — that's `remotion-brand-codify`.

It only plans + delegates.

## Per-project usage model

The package is shared infrastructure; each calling project supplies its own runtime config and API keys.

| Concern | Where it lives |
|---|---|
| Skill definitions | `~/.claude/skills/remotion-*` (symlinked → `Pi-Dev-Ops/skills/remotion-*`) — globally available. |
| Remotion Node project (compositions, brand configs, render entry) | `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/remotion-studio/` — single shared substrate. |
| Brand configs | `Synthex/packages/brand-config/src/brands/{slug}.ts` — one source of truth per brand, used by every project that renders for that brand. (Migrated from `Pi-Dev-Ops/remotion-studio/src/brands/` per RA-1985 / Synthex SYN-897.) |
| API keys (ElevenLabs, Telegram, Supabase, Linear, Remotion licence) | The **calling project's** `.env` / `.env.local`. Skills read `process.env` at render time. |
| Rendered MP4 output | The **calling project's** `.remotion-renders/` directory by default. Override with `--out=`. |

## Adding a new brand for your project

If your project (e.g. Synthex) needs to render for a brand that isn't yet in `src/brands/`:

1. Run `remotion-brand-research` against the brand's public sources.
2. Run `remotion-brand-codify` to produce `Synthex/packages/brand-config/src/brands/{slug}.ts`.
3. Extend the `BrandSlug` union in `Synthex/packages/brand-config/src/types.ts`.
4. Register in `Synthex/packages/brand-config/src/brands/index.ts`.
5. Run `npm run typecheck` from `Synthex/packages/brand-config/` (then `npm run build` to regenerate `dist/`).

Currently registered brands: `dr`, `nrpg`, `ra`, `carsi`, `ccw`, `synthex`, `unite`.


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
