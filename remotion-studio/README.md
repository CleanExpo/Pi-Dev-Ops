# remotion-studio

Pi-CEO multi-brand video framework. Renders branded explainer / promo / training videos for the portfolio (Disaster Recovery, NRPG, RestoreAssist, CARSI) and customer brands (CCW). Same composition, multiple brands, switched by input prop.

Skills that drive this project live at `Pi-Dev-Ops/skills/remotion-*/`. The Pi-Dev-Ops orchestrator routes any brief classified as `intent: "video"` to `remotion-orchestrator` first.

## Layout

```
remotion-studio/
├── src/
│   ├── index.ts                 # registerRoot
│   ├── Root.tsx                 # composition registry
│   ├── compositions/
│   │   └── Explainer.tsx        # 3-scene explainer (hook / body / cta)
│   ├── brands/
│   │   ├── types.ts             # BrandConfig schema
│   │   ├── ra.ts                # full
│   │   ├── dr.ts | nrpg.ts | carsi.ts | ccw.ts   # stubs
│   │   └── index.ts             # { brands } registry
│   ├── motion/index.ts          # signatureEntry, brandFadeIn, staggerStart
│   └── colour/index.ts          # contrast, readableOn, brandGradient
├── render/
│   ├── render.ts                # Node API entry — bundle + selectComposition + renderMedia
│   └── voiceover.ts             # ElevenLabs synthesis (cached, per-scene)
├── output/                      # MP4s (gitignored)
└── public/audio/                # synthesised voiceover MP3s (gitignored)
```

## Local install

```bash
cd Pi-Dev-Ops/remotion-studio
npm install
npm run typecheck
```

## Render — programmatic

```bash
ELEVENLABS_API_KEY=$ELEVENLABS_API_KEY \
  npx tsx render/render.ts \
    --comp=Explainer \
    --out=output/ra-nir-explainer-$(date +%s).mp4 \
    --jobId=ra-nir-$(date +%s) \
    --props='{"brand":"ra","hookSec":8,"ctaSec":8,"storyboard":[
      {"sceneId":"hook","durationSec":8,"voiceover":"...","onScreenText":"..."},
      {"sceneId":"body","durationSec":44,"voiceover":"...","onScreenText":"..."},
      {"sceneId":"cta","durationSec":8,"voiceover":"...","onScreenText":"..."}
    ]}'
```

Pass `--skipTts=true` to render without voiceover (silent + on-screen text only). The render still succeeds if `ELEVENLABS_API_KEY` is missing — `voiceover.ts` warns and skips synthesis.

## Render — Studio (preview)

```bash
npm run start
# opens http://localhost:3000 — pick the Explainer composition,
# tweak inputProps, scrub the timeline.
```

## Adding a new brand

1. Run `remotion-brand-research` skill on the company.
2. Run `remotion-brand-codify` to convert the dossier into `src/brands/{slug}.ts`.
3. Add the brand to the union in `src/brands/types.ts` (`BrandSlug`).
4. Register in `src/brands/index.ts`.
5. Run `npm run typecheck`.

## Adding a new composition

1. Run `remotion-marketing-strategist` for channel spec.
2. Run `remotion-screen-storyteller` for storyboard.
3. Run `remotion-designer` for layout spec.
4. Run `remotion-composition-builder` to author the TSX.
5. Register in `src/Root.tsx`.

## Environment

| Var | Required | Purpose |
|---|---|---|
| `ELEVENLABS_API_KEY` | optional (v1) | Voiceover synthesis. Missing = silent render. |
| `REMOTION_LICENSE_KEY` | required for commercial use | Remotion fair-source licence token. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | required for delivery | Used by `app.server.telegram_video`. |

## Licensing

Remotion is fair-source — companies with >3 employees using Remotion to generate revenue-impacting output need a Company licence. Buy at https://www.remotion.dev/pricing.

Fonts must be OFL / Apache / MIT. The `remotion-brand-codify` skill blocks Adobe Fonts (server-side render disallowed) and paid Google Fonts.
