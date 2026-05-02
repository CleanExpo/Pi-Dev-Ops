# Remotion Skills Package

Shared video-rendering capability for every project under `/Users/phill-mac/Pi-CEO/`. Skills authored once in Pi-Dev-Ops, available globally via symlinks, callable from any project (Synthex, Pi-SEO, RestoreAssist, future repos) with that project's own API keys.

## How to invoke from any project

From a Claude Code session in **any** working directory:

> Use the Remotion Skills Package — 60s LinkedIn explainer for Synthex about synthetic-data scale.

The orchestrator picks up the brief, classifies brand + composition + channel + duration, dispatches the wave plan, and renders to `<calling-project>/.remotion-renders/`.

## The 10 skills

| Skill | Role |
|---|---|
| `remotion-orchestrator` | Entry point. Reads brief, emits wave plan, dispatches. |
| `remotion-brand-research` | Gathers a brand's visual + verbal identity from public sources. |
| `remotion-brand-codify` | Writes the `BrandConfig` TypeScript file. |
| `remotion-designer` | Layout, type hierarchy, white-space, scene framing. |
| `remotion-colour-family` | WCAG-AA palette generation + dark variant. |
| `remotion-motion-language` | Brand-specific easing, signature motion (rise/sweep/iris/pulse/whip). |
| `remotion-screen-storyteller` | Per-scene voiceover + on-screen text + b-roll callouts. |
| `remotion-marketing-strategist` | Channel fit (LinkedIn / YouTube / Reels / training). |
| `remotion-composition-builder` | Authors / extends the Remotion `.tsx` composition. |
| `remotion-render-pipeline` | ElevenLabs voiceover → Remotion render → validate → ship. |

## Where each piece lives

| Concern | Location | Notes |
|---|---|---|
| Skill defs (canonical) | `Pi-Dev-Ops/skills/remotion-*/SKILL.md` | Edit here; symlinks pick up changes. |
| Skill defs (global) | `~/.claude/skills/remotion-*` → symlinks | Auto-discovered in every Claude session. |
| Remotion Node project | `Pi-Dev-Ops/remotion-studio/` | Compositions, brand configs, render entry. Single shared install. |
| Brand configs | `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.ts` | One file per brand. Currently: `dr`, `nrpg`, `ra`, `carsi`, `ccw`, `synthex`, `unite`. |
| Compositions | `Pi-Dev-Ops/remotion-studio/src/compositions/*.tsx` | v1: `Explainer`. v1.1+: `Intro`, `SocialAd`, `NIRReport`, `ProductDemo`. |
| Rendered output | `<calling-project>/.remotion-renders/` | Per-project, gitignored. Override with `--out=`. |

## Per-project API keys

Each calling project supplies its own keys via its own `.env` / `.env.local`. The skills read `process.env` at render time — they never assume Pi-Dev-Ops's keys.

```bash
# Your project's .env.local (Synthex example):
ELEVENLABS_API_KEY=sk_synthex_...
TELEGRAM_BOT_TOKEN=...                # optional — for delivery
TELEGRAM_CHAT_ID=...                  # optional
SUPABASE_URL=https://synthex....      # optional — signed-URL upload
SUPABASE_SERVICE_ROLE_KEY=...
LINEAR_API_KEY=lin_api_synthex_...    # optional — ticket creation
REMOTION_LICENSE_KEY=...              # required for commercial render
```

Skills behave gracefully when a key is absent:
- No `ELEVENLABS_API_KEY` → silent render with on-screen text only.
- No `TELEGRAM_*` → skip Telegram step; MP4 still on disk.
- No `SUPABASE_*` → skip cloud upload.
- No `LINEAR_API_KEY` → skip ticket creation.
- No `REMOTION_LICENSE_KEY` → fine for personal / dev use; commercial output requires it.

## Adding a new brand (e.g. for a customer or a new project)

1. From your project session: *"Use `remotion-brand-research` for `<brand-name>`."*
2. Review the dossier under `Pi-Dev-Ops/remotion-studio/.research/brand-{slug}-{date}.md`.
3. *"Use `remotion-brand-codify` to produce `src/brands/{slug}.ts`."*
4. Extend `BrandSlug` in `src/brands/types.ts` and register in `src/brands/index.ts`.
5. `cd Pi-Dev-Ops/remotion-studio && npm run typecheck`.
6. Render: *"Use the Remotion Skills Package — 30s social ad for `{slug}`."*

## Adding a new composition type (e.g. `SocialAd`)

1. *"Use `remotion-marketing-strategist` for a 30s Instagram Reel."*
2. *"Use `remotion-screen-storyteller` for `<topic>`."*
3. *"Use `remotion-designer` for the SocialAd layout."*
4. *"Use `remotion-composition-builder` to create `src/compositions/SocialAd.tsx`."*
5. Builder registers it in `src/Root.tsx` and runs `tsc`.

## Verification (already passed in initial ship)

- `npx tsc --noEmit` — clean
- `python3 -m py_compile` — clean
- End-to-end smoke render — `output/ra-nir-smoke.mp4` (1920×1080, h264+aac, 60s, 3.1 MB) ✓
- Intent classifier — video briefs → `intent: "video"` ✓

## Licensing reminder

Remotion is fair-source. Commercial use across multiple brands requires the Company licence. Buy at https://www.remotion.dev/pricing before any client-facing render ships. Fonts must be OFL / Apache / MIT — `remotion-brand-codify` blocks Adobe Fonts and paid Google Fonts at PR time.
