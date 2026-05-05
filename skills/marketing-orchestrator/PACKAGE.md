# Marketing Skills Package

Shared marketing capability for every project under `/Users/phill-mac/Pi-CEO/`. 10 skills authored once in Pi-Dev-Ops, available globally via symlinks, callable from any project (Synthex, Pi-SEO, RestoreAssist, future repos) with that project's own API keys. Composes with the **Remotion Skills Package** for any video deliverable.

## How to invoke from any project

From a Claude Code session in **any** working directory:

> Use the Marketing Skills Package — full launch campaign for Synthex on LinkedIn, target ML platform teams, 30-day window.

Or for a single artifact:

> Use marketing-copywriter for a Synthex landing page targeting ML engineers.

The orchestrator picks up the brief, classifies (campaign type / brand / audience / channels / timeline), dispatches the wave plan, and writes outputs to `<calling-project>/.marketing/`.

## The 10 skills

| Skill | Role |
|---|---|
| `marketing-orchestrator` | Entry point. Reads brief, emits wave plan, dispatches. |
| `marketing-campaign-planner` | Campaign design — objectives, audience, channels, timeline, budget, KPIs. |
| `marketing-positioning` | Value prop, JTBD, competitive positioning, messaging hierarchy, anti-positioning. |
| `marketing-icp-research` | Ideal Customer Profile — firmographics, roles, pain hierarchy, vocabulary, watering holes, buying process. |
| `marketing-channel-strategist` | Channel mix + per-channel cadence. Sets video aspect ratio + duration for Remotion handoffs. |
| `marketing-copywriter` | Long-form copy — landing pages, blog posts, email sequences, ad copy. |
| `marketing-seo-researcher` | Keyword + SERP + content-gap + cluster pyramid. |
| `marketing-social-content` | Short-form for LinkedIn / X / Instagram / TikTok. Cross-pack dispatches video to `remotion-orchestrator`. |
| `marketing-launch-runbook` | T-30 → T+30 launch playbook with per-day owners, dependencies, gates, contingencies, war-room. |
| `marketing-analytics-attribution` | UTM scheme + attribution model + dashboard spec + pre-launch checklist + retro template. |

## Composition with Remotion Skills Package

Marketing pack does NOT author video. Whenever a deliverable is video, the marketing skill emits the brief and dispatches `remotion-orchestrator` with `{brand, composition, channel, durationSec, topic, storyboard?}`. The Remotion pack handles storyboard / motion / render. Marketing handles strategy / copy / non-video.

Cross-pack handoff points:
- `marketing-channel-strategist` → `remotion-orchestrator` (channel determines aspect ratio + duration).
- `marketing-social-content` → `remotion-orchestrator` (every video slot).
- `marketing-launch-runbook` → `remotion-orchestrator` (every video drop on the calendar).
- `marketing-copywriter` → `remotion-orchestrator` (CTA video / hero animation).

## Where each piece lives

| Concern | Location | Notes |
|---|---|---|
| Skill defs (canonical) | `Pi-Dev-Ops/skills/marketing-*/SKILL.md` | Edit here; symlinks pick up changes. |
| Skill defs (global) | `~/.claude/skills/marketing-*` → symlinks | Auto-discovered in every Claude session. |
| Substrate (templates + frameworks) | `Pi-Dev-Ops/marketing-studio/` | Templates for campaigns, runbooks, emails, landing pages. JTBD / positioning / ICP canvases. |
| Brand configs (shared with Remotion) | `Synthex/packages/brand-config/src/brands/{slug}.ts` | Single source of truth. Refine via `remotion-brand-research` + `remotion-brand-codify`. (Migrated from `Pi-Dev-Ops/remotion-studio/src/brands/` per RA-1985.) |
| UTM helper | `Pi-Dev-Ops/marketing-studio/scripts/utm-builder.ts` | TS + CLI. |
| Per-job artifacts | `<calling-project>/.marketing/` | Per-project, gitignored. Falls back to `marketing-studio/outputs/{job-id}/` if no calling project. |

## Per-project API keys

Each calling project supplies its own keys. Skills read `process.env` at runtime — never assume Pi-Dev-Ops's keys.

```bash
# Your project's .env.local (Synthex example):
ANTHROPIC_API_KEY=sk-ant-...           # for copy + positioning + ICP refinement
OPENAI_API_KEY=sk-...                  # alternative LLM
PERPLEXITY_API_KEY=pplx-...            # ICP + SEO + competitor research
LINEAR_API_KEY=lin_api_synthex_...     # campaign tickets
TELEGRAM_BOT_TOKEN=...                 # war-room delivery
TELEGRAM_CHAT_ID=...
RESEND_API_KEY=re_...                  # (optional) email send
GOOGLE_ANALYTICS_PROPERTY_ID=...       # dashboard wiring
POSTHOG_API_KEY=phc_...                # event-based attribution
```

Graceful degradation when keys are absent:
- No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` → emits scaffolds + placeholders, refuses to fabricate copy.
- No `PERPLEXITY_API_KEY` → ICP / SEO / competitive map ship as seed-only with explicit "needs primary research" markers.
- No `LINEAR_API_KEY` → markdown checklists only.
- No analytics keys → tool-agnostic dashboard spec.
- No keys block the structural artifact — it's always emitted.

## Adding a new brand

Brand voice is shared with Remotion. To add or refine a brand:

1. *"Use `remotion-brand-research` for `<brand-name>`."*
2. Review the dossier under `Pi-Dev-Ops/remotion-studio/.research/`.
3. *"Use `remotion-brand-codify` to produce `src/brands/{slug}.ts`."*
4. Both packs immediately use the new BrandConfig.

Currently registered brands: `dr`, `nrpg`, `ra`, `carsi`, `ccw`, `synthex`, `unite`.

## End-to-end example — full Synthex launch

Brief: *"Use the Marketing Skills Package — full product launch for Synthex on 2026-05-15. ML platform teams. LinkedIn primary. Standard tier."*

Wave 1 (parallel):
- `marketing-positioning` → `synthex-launch/positioning.md`
- `marketing-icp-research` → `icp/synthex-2026-04-28.md`

Wave 2 (parallel, depends on wave 1):
- `marketing-channel-strategist` → `channel-plan.json` (LinkedIn primary, YouTube + email + partnerships)
- `marketing-seo-researcher` → `seo/synthex-launch-keywords.json`

Wave 3 (parallel, depends on wave 2):
- `marketing-copywriter` (×3 in parallel) → landing-spec, email-sequence, blog-post-pillar
- `marketing-social-content` → `social/{linkedin-1...12}.md` + `x/{thread-1}.md`
- `marketing-analytics-attribution` → `utm-scheme.md`, `attribution-model.md`, `dashboard-spec.json`

Wave 4 (parallel, depends on wave 3):
- `remotion-orchestrator` (cross-pack) — dispatched 4 video deliverables (60s explainer, 30s social cut, 15s teaser, 90s case-study)
- `marketing-launch-runbook` → `runbook.md` + `runbook.json` with T-30 → T+30 calendar

Wave 5 (gate at T-7):
- Pre-launch checklist (analytics-attribution) — HARD-STOP if any UTM / tracking / asset is missing.

T-0 + amplify + measure phases run from the runbook.

## Voice + content rules (enforced by every skill)

Inherits from Pi-CEO global content rules:
- No first-person plurals (we / our / I / us / my).
- No AI-filler words (delve, tapestry, leverage, robust, seamless, elevate, landscape).
- Every paragraph answers a specific question.
- Cadence per `BrandConfig.voice.requiredCadence`.
- Forbidden words per `BrandConfig.voice.forbiddenWords`.
- `BrandConfig.doNot` is inviolable.

Voice lint runs at the end of every copywriter / social-content output. Any forbidden-words hits block the artifact.

## Verification

- 10 SKILL.md files exist + `tsc --noEmit` clean on the UTM helper.
- Symlinks resolve through `~/.claude/skills/marketing-*`.
- Substrate templates render readable markdown.
- See the Remotion package's `PACKAGE.md` for the cross-pack dispatch contract.
