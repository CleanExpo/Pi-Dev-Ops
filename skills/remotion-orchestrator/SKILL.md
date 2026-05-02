---
name: remotion-orchestrator
description: ENTRY POINT for the Remotion Skills Package. Use the moment a brief mentions "remotion skills package", "remotion package", "use remotion", or any of the video keywords — video, explainer, ad, promo, reel, intro, social cut, 60s/30s/15s spot, or any rendered marketing/training video for one of the portfolio brands (DR, NRPG, RestoreAssist/RA, CARSI, CCW) or for a customer brand. Globally available across every project under /Users/phill-mac/. Reads the brief, classifies intent (composition type, brand, channel, duration), emits a wave-plan JSON, and dispatches the right sub-skills in topological order. Always invoked first.
automation: automatic
intents: video, explainer, ad, promo, reel, intro, social, render, marketing-video, training-video, 60s, 30s, 15s, remotion, remotion-skills-package
---

# remotion-orchestrator — Remotion Skills Package entry point

Single entry point for the Remotion Skills Package — a set of 10 sibling skills (`remotion-orchestrator`, `remotion-brand-research`, `remotion-brand-codify`, `remotion-designer`, `remotion-colour-family`, `remotion-motion-language`, `remotion-screen-storyteller`, `remotion-marketing-strategist`, `remotion-composition-builder`, `remotion-render-pipeline`) installed globally at `~/.claude/skills/remotion-*` (symlinked to `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/skills/remotion-*`). Available in every project, not just Pi-Dev-Ops.

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
| Brand configs | `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.ts` — one source of truth per brand, used by every project that renders for that brand. |
| API keys (ElevenLabs, Telegram, Supabase, Linear, Remotion licence) | The **calling project's** `.env` / `.env.local`. Skills read `process.env` at render time. |
| Rendered MP4 output | The **calling project's** `.remotion-renders/` directory by default. Override with `--out=`. |

## Adding a new brand for your project

If your project (e.g. Synthex) needs to render for a brand that isn't yet in `src/brands/`:

1. Run `remotion-brand-research` against the brand's public sources.
2. Run `remotion-brand-codify` to produce `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.ts`.
3. Extend the `BrandSlug` union in `src/brands/types.ts`.
4. Register in `src/brands/index.ts`.
5. Run `npm run typecheck` from `Pi-Dev-Ops/remotion-studio/`.

Currently registered brands: `dr`, `nrpg`, `ra`, `carsi`, `ccw`, `synthex`, `unite`.
