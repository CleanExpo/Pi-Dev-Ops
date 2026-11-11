# Decision Room: composition file structure and episode schema

Moved from SKILL.md. Where scene code lives and what the episode JSON contains.

## Composition File Structure

```
D:\Claude-Code-Remotion\RestoreAssist\src\
├── shared\
│   ├── brand.tsx          — brand tokens, LogoMark, GlowOrb, GridOverlay, CyanRule
│   ├── motion.ts          — all named easing curves and spring configs
│   ├── typography.tsx     — Text components (Display, Heading, Body, Mono, Label)
│   └── transitions.tsx    — SceneTransition, ActTransition, WhiteFlash
├── boardroom\
│   ├── ColdOpenScene.tsx
│   ├── ProblemScene.tsx
│   ├── MethodScene.tsx    — takes method index + content + screenshot path
│   ├── SWOTScene.tsx      — four-beat kinetic sequence
│   ├── DecisionScene.tsx  — full-bleed statement + SHIPPED reveal
│   └── ProductScene.tsx   — screenshot cross-dissolve sequence
├── BoardroomComposition.tsx  — assembles all scenes, reads episode JSON
├── VideoGuideComposition.tsx — existing (unchanged)
└── index.ts               — registers both compositions
```

Each scene file is under 200 lines. If it exceeds 200 lines, split into sub-components.

---

## Episode Content Schema

Episode content lives in `content/resources/{slug}.json`. The Decision Room episodes
extend the existing schema with these new fields:

```typescript
interface DecisionRoomEpisode {
  slug: string
  title: string           // "The Sketch Tool Decision"
  episodeNumber: number   // 1–8
  coldOpenStat: string    // single striking line, max 12 words
  problem: {
    headline: string      // max 8 words
    facts: string[]       // 2–3 facts, each max 20 words
    ticketRef?: string    // "RA-93" etc.
  }
  methods: Array<{
    name: string          // max 6 words, no product names
    description: string   // max 30 words
    screenshotName?: string // filename from public/screenshots/
    consequence?: string  // "if chosen: ..." max 20 words
  }>
  swot: {
    strengths: [string, string]
    weaknesses: [string, string]
    opportunities: [string, string]
    threats: [string, string]
  }
  decisionStatement: string  // THE sentence. Max 20 words. This is everything.
  shippedScreenshot: string  // filename from public/screenshots/
  productScreenshots: string[] // 3–4 filenames, cross-dissolve sequence
  videoScript: string        // ElevenLabs TTS script with [PAUSE] markers
  tags: string[]
}
```
