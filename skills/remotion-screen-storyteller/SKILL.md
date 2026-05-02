---
name: remotion-screen-storyteller
description: Writes the on-screen script for a video — scene-by-scene voiceover, on-screen text, b-roll callouts, and CTA. Triggered when the brief is a goal or topic but lacks scene structure. Produces a Storyboard JSON consumed by remotion-composition-builder and remotion-render-pipeline (for ElevenLabs voiceover synthesis).
automation: automatic
intents: storyboard, script, scene-breakdown
---

# remotion-screen-storyteller

The words and the cuts. Not the design (designer), not the build (composition-builder).

## Triggers

- Brief describes a goal/topic without scenes ("60s explainer for RA's NIR feature").
- User asks to rewrite voiceover or punch up a scene.

## Inputs

- `brand` — for voice constraints (tone, forbidden words, cadence)
- `topic` — what the video is about
- `durationSec` — total runtime
- `channel` — LinkedIn / YouTube / Instagram / training (sets pacing)
- Channel spec from `remotion-marketing-strategist` if available

## Method

1. **Three-act default**: hook (~13% of duration) / body (~74%) / CTA (~13%). For 60s → 8/44/8s.
2. **Hook line** — single declarative sentence stating the problem or the surprising fact. Reads in ≤3.5 seconds out loud.
3. **Body** — 2-4 micro-scenes, each ≤15s, each ending with a complete thought. Avoid lists with more than 3 items.
4. **CTA** — brand name + tagline + action verb. Reads in ≤4 seconds.
5. **Voice constraints** — every line passes `BrandConfig.voice.forbiddenWords` filter (no `we / our / I / us / my` per Pi-CEO conventions; brand-specific bans like CCW's "cheapest").
6. **Cadence** — short cadence brands (RA, CCW) prefer ≤12-word sentences; medium (DR, NRPG, CARSI) up to 18.

## Output

```jsonc
{
  "storyboard": [
    {
      "sceneId": "hook",
      "durationSec": 8,
      "voiceover": "Australia ships hundreds of restoration report formats. One should be enough.",
      "onScreenText": "Hundreds of report formats.\nOne should be enough.",
      "broll": null
    },
    { "sceneId": "body", "durationSec": 44, "voiceover": "...", "onScreenText": "...", "broll": "logos/ra/nir-mockup.png" },
    { "sceneId": "cta",  "durationSec": 8,  "voiceover": "RestoreAssist. One National Inspection Standard.", "onScreenText": "..." }
  ]
}
```

`onScreenText` may differ from `voiceover` — terser, with line breaks for visual rhythm.

## Boundaries

- Never write more on-screen text than fits the screen (rough rule: ≤14 words at 72pt).
- Never include emojis in voiceover (TTS pronunciation is unreliable).
- Never assume a music bed exists — write so the video stands silent.

## Hands off to

`remotion-composition-builder` (uses the storyboard) and `remotion-render-pipeline` (synthesises voiceover via ElevenLabs).
