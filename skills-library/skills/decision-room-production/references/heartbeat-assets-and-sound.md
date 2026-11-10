# Decision Room: heartbeat map, asset pipeline and sound cues

Moved from SKILL.md. Emotional arc, real-asset rules and voiceover pacing notes.

## The Heartbeat Map

This is the emotional arc for a complete episode. Every scene should be able to point to a
position on this arc:

```
0:00  ●  Weight (cold open stat lands — silence before the brand)
0:09  ↗  Authority (RestoreAssist mark — "we know this world")
0:20  ↗  Urgency (problem stat 2 — the scale of the issue)
0:40  →  Curiosity (methods begin — "how did they approach it?")
1:10  →  Consideration (method 2 — the alternative)
1:40  ↘  Doubt (method 3 dimming — "none of these are perfect")
2:00  ↘  Tension (SWOT — strengths and weaknesses in visual conflict)
2:30  ●  Maximum tension (weaknesses and threats — the pivot)
2:50  ↗  Resolution energy (opportunities rise)
3:15  ↗↗ Release (decision statement — one sentence, full bleed)
3:30  ●● Satisfaction (the product, running live)
4:10  →  Confidence (product screen sequence)
4:45  ↗  Action (URL, final mark)
5:00  ●  Silence (black frame — let it land)
```

---

## Asset Pipeline

### Screenshots
The `capture-screenshots.ts` script captures 1920×1080 PNGs of the live app.
Assets live in `public/screenshots/`. Use these episode-to-asset mappings:

```
Episode 1 (Sketch):         inspection-sketch-tab.png
Episode 2 (IICRC):          inspection-detail.png (moisture tab)
Episode 3 (AI Scope):       inspection-detail.png (scope tab)
Episode 4 (Integration):    dashboard.png + dashboard-integrations (capture separately)
Episode 5 (Property Data):  dashboard-inspections.png
Episode 6 (Mobile):         capture mobile simulator screenshots separately
Episode 7 (Dev+AI):         dashboard.png + a code editor screenshot
Episode 8 (Moisture Map):   inspection-moisture-tab.png
```

In the composition, load screenshots via Remotion's `staticFile()`:
```tsx
<Img src={staticFile('/screenshots/inspection-sketch-tab.png')}
     style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
```

### Code Snippets
Code shown on screen must be **real code from the codebase**, not invented.
Pull from actual source files. Apply a dark code block:
```
background: #0d1117  (GitHub dark)
border-left: 3px solid #06b6d4
border-radius: 8px
padding: 24px 28px
font: JetBrains Mono 16px
```
Reveal lines one at a time, 4 frames apart, top to bottom. Max 8 lines visible at once.

### Linear Ticket Citations
When referencing a build decision, show the ticket as a lower-third source badge:
```
RA-266 · Moisture Drying Progress Chart · Done 2026-03-30
```
Font: JetBrains Mono 12px, opacity 55%, bottom-left, 32px from edge.
Fade in at 40% opacity, hold 6 seconds, fade out. Never sits over key content.

---

## Sound Design Cues (for voiceover sync)

Sound is not in scope for Remotion rendering (ElevenLabs handles the voiceover).
However, instruct ElevenLabs with these pacing notes embedded in the script:

```
[PAUSE 1.5s]    — cold open stat (silence after the number)
[PAUSE 0.8s]    — between each method
[PAUSE 2.0s]    — before decision statement (maximum anticipation)
[PAUSE 1.0s]    — after "SHIPPED" moment
[PAUSE 0.5s]    — between product screens
[SLOW DOWN]     — decision statement should be delivered 20% slower than body
[EMPHASIS]      — marks a word that should be louder/stressed
```
