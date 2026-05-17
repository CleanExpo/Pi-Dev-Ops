---
channel: [linkedin, instagram-reels]
brand: ra
job: ra-practitioner-story-series-2026-05-12
slot: 7-of-7
assetType: video
voice: klark-brown
hashtags: [RestorationScope, DocumentationDefence, ANZRestoration]
videoDispatched: true
sourcePost: linkedin-4.md
dispatch:
  skill: remotion-orchestrator
  composition: SocialAd
  brand: ra
  aspect: 9:16
  resolution: 1080x1920
  durationSec: 30
  fps: 30
  voiceover:
    provider: elevenlabs
    voiceId: EXAVITQu4vr4xnSDxMaL
    style: narration
    locale: en-AU
  motion:
    signature: sweep
    transitionFrames: 14
  outputPath: remotion-studio/out/ra/practitioner-story-04-bathroom-to-wholehouse-2026-05-12.mp4
---

# Reel — Scope Grew 6x. Every Line Item Held.

Adapted from `linkedin-4.md`. 30-second vertical Reel for LinkedIn-native + Instagram cross-post. Single-narrator, mono-stamped readings, lime accent on dollar figures.

## Caption (≤125 chars, above-fold)

Scope grew 6x. Every line item held. The bathroom job that became a whole-house job — and held up.

Hashtags: #RestorationScope #DocumentationDefence #ANZRestoration #IICRC #Restopreneur

## Storyboard

### Scene 1 — Hook (0.0s → 3.0s, 0 → 90 frames)
- **Surface:** `colour.primary` `#0E7C7B` full-bleed.
- **Headline:** "Scope grew 6x." — Inter ExtraBold 96pt, `colour.neutral.50`.
- **Sub-stat:** "Every line item held." — Inter ExtraBold 64pt, `colour.accent` `#C5E063`.
- **Logo:** RestoreAssist primary mark, top-left, 48px safe area.
- **Motion:** Headline enters via `signature: sweep`, 18 frames. Sub-stat sweeps in at frame 28.
- **VO:** "Failed mixer valve. Single bathroom."

### Scene 2 — Initial scope (3.0s → 9.0s, 90 → 270 frames)
- **Surface:** `colour.secondary` `#2A3D45`.
- **B-roll plate (optional):** static interior — bathroom doorway, neutral lighting. If unavailable, render the typographic card as below.
- **On-screen text:** "Day 1: bathroom strip-out" — Inter ExtraBold 56pt, `colour.neutral.50`.
- **Mono chip (bottom-left):** `JOB-AUD-7140` in JetBrains Mono Medium on `colour.neutral.100` chip, 6px radius.
- **Stat callout:** "$7,800" — Inter ExtraBold 96pt, `colour.accent`.
- **Motion:** sweep transition in from Scene 1. Stat callout enters at frame 150 with a 12-frame counter ramp.
- **VO:** "Adjuster signed at seven-thousand-eight-hundred."

### Scene 3 — Moisture readings appear (9.0s → 15.0s, 270 → 450 frames)
- **Surface:** `colour.neutral.50` `#F5F7F8` (light card for clinical contrast).
- **Headline:** "Then the readings came in." — Inter ExtraBold 64pt, `colour.neutral.900`.
- **Two stat rows, stacked, each on a `colour.neutral.100` card, 12px radius:**
  - Row 1 — `[D+3 · HALLWAY PLATE]` mono chip + `36.2%` `colour.semantic.warning` `#E0A800`.
  - Row 2 — `[D+4 · LIVING SUB-FLOOR]` mono chip + `41.0%` `colour.semantic.danger` `#C0392B`.
- **Motion:** Row 1 sweeps in frame 290. Row 2 sweeps in frame 360. Each value counter-ramps 8 frames.
- **VO:** "Hallway plate, thirty-six-point-two. Living room sub-floor, forty-one."

### Scene 4 — NIR provenance (15.0s → 22.0s, 450 → 660 frames)
- **Surface:** `colour.primary` `#0E7C7B`.
- **Headline:** "Every reading stamped." — Inter ExtraBold 72pt, `colour.neutral.50`.
- **Mono chip row:** three chips across — `READING`, `PHOTO`, `JOB CODE` — each on `colour.accent` `#C5E063` with `colour.secondary` text.
- **Sub-line:** "One continuous record." — Inter Regular 32pt, `colour.neutral.50`.
- **Motion:** Chips sweep in left-to-right, 8 frames stagger between each.
- **VO:** "Every revised line item stamped, dated, anchored to a job code."

### Scene 5 — Final stat (22.0s → 27.0s, 660 → 810 frames)
- **Surface:** `colour.secondary` `#2A3D45`.
- **Hero stat:** "$47,000" — Inter ExtraBold 144pt, `colour.accent`. Counter ramp 60 → 47000 over 18 frames.
- **Sub-stat:** "Paid in full. Zero second visit." — Inter ExtraBold 40pt, `colour.neutral.50`.
- **Motion:** Stat sweeps in at frame 660, counter ramp completes by frame 678. Sub-stat sweeps in at frame 700.
- **VO:** "Final scope: forty-seven thousand. Paid without a second site visit."

### Scene 6 — Brand close + CTA (27.0s → 30.0s, 810 → 900 frames)
- **Surface:** `colour.primary` `#0E7C7B`.
- **Logo:** RestoreAssist primary mark, centred-left, 64px from edge.
- **Tagline:** "One National Inspection Standard." — Inter ExtraBold 56pt, `colour.neutral.50`.
- **CTA chip:** "Documentation that defends itself." — `colour.accent` chip, `colour.secondary` text, Inter ExtraBold 28pt, 8px radius, bottom-centre.
- **Motion:** Logo + tagline sweep in frame 810. CTA chip slides up from below at frame 850.
- **VO:** silent — visual close only.

## Voiceover script (30s, ElevenLabs Sarah, AU/UK, narration)

```
Failed mixer valve. Single bathroom. Adjuster signed at seven-thousand-eight-hundred.

Then the moisture readings came in. Hallway plate, thirty-six-point-two. Living room sub-floor, forty-one.

Every revised line item stamped, dated, anchored to a job code.

Final scope: forty-seven thousand. Paid without a second site visit.
```

Pacing: ~50 words, ~150 wpm. Natural pauses at scene transitions. No filler, no marketing tone — read as a field briefing.

## Composition file target

```
remotion-studio/src/compositions/PractitionerStory04-BathroomToWholeHouse.tsx
```

Register in `remotion-studio/src/Root.tsx` as composition id `practitioner-story-04`. Width 1080, height 1920, fps 30, durationInFrames 900.

## Render pipeline acceptance criteria

- Total duration: 30.00s ±0.05s (900 frames @ 30fps).
- Codec: H.264, AAC audio, MP4 container.
- File size: ≤ 20 MB (LinkedIn vertical limit).
- Resolution: 1080×1920 (square pixel ratio).
- Voiceover audible across full duration, peak −3 dB, no clipping.
- No frame contains the abbreviation "RA" in any on-screen text (brand `doNot` rule).
- Only three colours per scene (per `ra.design.md` §5).
- Lime `#C5E063` used only on dollar figures and the final CTA chip.

## Dispatch payload (for `remotion-orchestrator`)

```json
{
  "skill": "remotion-orchestrator",
  "composition": "SocialAd",
  "compositionId": "practitioner-story-04",
  "brand": "ra",
  "durationSec": 30,
  "aspect": "9:16",
  "fps": 30,
  "storyboardFile": ".marketing/social/ra-practitioner-story-series-2026-05-12/video-1.storyboard.md",
  "voiceover": {
    "provider": "elevenlabs",
    "voiceId": "EXAVITQu4vr4xnSDxMaL",
    "locale": "en-AU",
    "script": "Failed mixer valve. Single bathroom. Adjuster signed at seven-thousand-eight-hundred. Then the moisture readings came in. Hallway plate, thirty-six-point-two. Living room sub-floor, forty-one. Every revised line item stamped, dated, anchored to a job code. Final scope: forty-seven thousand. Paid without a second site visit."
  },
  "output": "remotion-studio/out/ra/practitioner-story-04-bathroom-to-wholehouse-2026-05-12.mp4",
  "channels": ["linkedin", "instagram-reels"]
}
```
