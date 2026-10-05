---
name: decision-room-production
description: "Production bible for RestoreAssist \"Decision Room\" episodes — cinematic Remotion compositions at senior production house quality. Use this skill whenever writing, designing, or rendering any Decision Room episode. Covers the full stack: cold open philosophy, frame-precise timing charts, per-act colour grading, kinetic typography, heartbeat emotional arc, real asset pipeline (Playwright screenshots, code reveals, Linear ticket citations), sound design cues, and the Remotion TSX patterns that encode all of it. Do NOT produce generic bullet-card output. Every frame must be intentional."
---

# Decision Room — Production Bible

## The One Rule

A production team with 15 years behind them does not fill time — they **earn** every second.
Before writing a single line of Remotion TSX, ask: *what is the audience feeling at this frame,
and what do we want them to feel at the next one?* If you cannot answer that, the scene is not
ready to write.

This is not a technical guide format. It is a **documentary about the craft of building
software for the restoration industry** — one major decision per episode, told with the
discipline and intention of a broadcast journalism package.

---

## Episode Structure — 5 Minutes (9,000 frames @ 30fps)

Each episode is built on five acts. The timing below is **non-negotiable** — it encodes the
emotional arc. Do not flatten it into uniform sections.

```
ACT 0 — COLD OPEN          frames    0 –   270    (0:00 – 0:09)
ACT 1 — PROBLEM             frames  270 –  1350    (0:09 – 0:45)
ACT 2 — METHODS             frames 1350 –  3600    (0:45 – 2:00)
ACT 3 — SWOT                frames 3600 –  5850    (2:00 – 3:15)
ACT 4 — DECISION GRANTED    frames 5850 –  7920    (3:15 – 4:24)
ACT 5 — PRODUCT ALIVE       frames 7920 –  9000    (4:24 – 5:00)
```

See `references/timing-chart.md` for the frame-by-frame beat map of each act.

---

## Act Philosophy

### ACT 0 — Cold Open (9 seconds)
**No logo. No title. No greeting.**
Open on black. A single data point or quote — one line — fades in from nothing.
This is the weight of the problem before the audience knows they are watching anything.

Examples that work:
- *"47% of Australian restoration claims are delayed by documentation errors."*
- *"The floor plan uploaded. The compliance report didn't."*
- *"It took 4 hours to write a scope that should take 4 minutes."*

The line sits for 4 seconds. Then a slow white flash — not a logo reveal — a *breath*.
The RestoreAssist mark fades in at 8 seconds. Episode number badge, bottom-left, no animation.

### ACT 1 — The Problem (36 seconds)
**Establish urgency. Do not explain yet.**
Two or three facts that make the problem vivid — visual, not abstract.
Use the real industry numbers. Real Linear ticket counts. Real timestamps from the build log.

The headline arrives at frame 540 (18 seconds in) — large, single-colour, full width.
Sub-headline at frame 720 (24 seconds) — muted, half-size, fade-up.

Colour temperature: **cold** — desaturated navy, cyan at 60% opacity, almost grey.
This is the world *before* the decision.

### ACT 2 — Methods (75 seconds)
**One method = one screen. Each gets 20–25 seconds.**
Not a list. A reveal. Each method enters from the left at 80% opacity, holds, then dims to 40%
as the next method arrives. The dimming signals "we considered this and moved on."

For 3 methods: 3 screens × 25 seconds = 75 seconds, perfect.
For 2 methods: pad each to 37 seconds with a *consequence reveal* — what would have happened
if we had chosen this.

Pull **real screenshots** from `public/screenshots/` for relevant methods. Scale to 85%,
apply a 2px cyan border, slight drop shadow. Never use placeholder graphics.

Colour temperature: **neutral** — full navy, cyan at 100%.

### ACT 3 — SWOT (75 seconds)
**The tension act. This is the pivot.**
Do not use a 2×2 grid. The SWOT is delivered as a **four-beat kinetic sequence**:

- Strengths enter from the left (warm — lean toward amber undertone)
- Weaknesses enter from the right simultaneously, pushing back (cooler, slight red undertone)
- Opportunities rise from below (this is resolution energy — let it breathe)
- Threats descend from above (brief — 8 seconds only — do not linger on fear)

Each quadrant has one headline and two supporting facts maximum.
The visual tension between left and right entering simultaneously is what makes SWOT feel like
a genuine decision, not a checklist.

Colour temperature: **in flux** — this is the only act where the grade shifts mid-act.

### ACT 4 — Decision Granted (69 seconds)
**The release. One sentence. Full bleed.**
The decision is stated in a single sentence. No sub-copy. No bullet points.
The sentence enters at 100% scale from 85%, spring-settled, 0.6 second duration.

At frame 6300 (15 seconds into this act), cut to black for 12 frames.
Then: the feature, running live in the product. A real screenshot, full 1920×1080, no border.
The RestoreAssist watermark, bottom-right, 22px, 40% opacity.

The word **SHIPPED** fades in over the screenshot at 60% opacity in Inter Display 700, tracking
+6, all caps, cyan — centred, bottom third.

Colour temperature: **warm** — navy pulls toward 20% amber, cyan at full brightness.

### ACT 5 — Product Alive (36 seconds)
**Show the thing working. Then release the audience.**
Real screenshot sequence: 3–4 product screens, cross-dissolving every 8 seconds.
Progress bar depletes. URL badge builds in. Episode badge, bottom-left, same as cold open.

Final frame: black. RestoreAssist mark. `restoreassist.com.au`. Nothing else.

---

## Colour System

The grade shifts across acts to carry emotional weight. Never use flat values — always
interpolate between act colours at scene transitions (15-frame cross-fade minimum).

```
                BACKGROUND          CYAN              BODY TEXT
Cold Open:      #0a0f1a             #0891b2 (60%)     #9ca3af
Act 1 Problem:  #101827             #06b6d4 (65%)     #d1d5db
Act 2 Methods:  #152338 (base)      #06b6d4 (100%)    #f4f5f6
Act 3 SWOT:     shifts              see below         varies
  Strengths:    warm left half      #06b6d4           #f4f5f6
  Weaknesses:   #1a1020 right half  #9333ea (30%)     #e2e8f0
  Opportunities:#0f2318             #34d399           #f4f5f6
  Threats:      #1a100f             #f87171 (50%)     #fca5a5
Act 4 Decision: #1a1508             #06b6d4 (100%)    #fef3c7 (warm)
Act 5 Product:  #0f172a             #06b6d4           #f4f5f6
```

Full hex values with interpolation keyframes: `references/color-system.md`

---

## Typography System

Never use Segoe UI as a primary display face. The RestoreAssist Decision Room uses:

```
Display:   Inter Display 800   — headlines, decision statement, cold open stat
           size 72–96px, tracking -2.5, line-height 0.95
Heading:   Inter 700            — act titles, method names, SWOT quadrant headers
           size 40–52px, tracking -1.0, line-height 1.1
Body:      Inter 400            — supporting facts, bullet content
           size 20–24px, tracking 0, line-height 1.6
Mono:      JetBrains Mono 400   — code snippets, ticket numbers, timestamps
           size 16–18px, tracking +0.5
Label:     Inter 500 ALL CAPS   — episode number, act labels, "SHIPPED"
           size 12–14px, tracking +3.0, opacity 60–80%
```

In Remotion, load via CSS `@import` in the Remotion config or inline style injection.
Fall back to `"Inter", "system-ui", sans-serif` if font loading fails.

---

## Motion Language

Spring animations should be **rare and intentional** — not the default. Use them only for
the Decision Granted reveal and CTA scale-in. Everything else uses one of these:

```
REVEAL (content entering):
  easing: cubic-bezier(0.16, 1, 0.3, 1)   — fast out, slow settle
  duration: 18–24 frames
  translateY: 28px → 0, opacity: 0 → 1

EMPHASIS (stat/headline):
  easing: cubic-bezier(0.34, 1.56, 0.64, 1)  — slight overshoot
  duration: 14 frames
  scale: 0.92 → 1.0, opacity: 0 → 1

DISMISS (method dimming when next arrives):
  easing: linear
  duration: 12 frames
  opacity: current → 40%

SCENE TRANSITION (act-to-act):
  white flash at 8% opacity for 3 frames, then cross-fade 15 frames
  Do NOT use the full black wipe — that kills pacing

DECISION SNAP (the moment):
  spring({ damping: 14, stiffness: 180 }) — fast, decisive
  scale: 0.88 → 1.0

SCREENSHOT REVEAL:
  easing: cubic-bezier(0.25, 0.46, 0.45, 0.94)
  duration: 30 frames
  translateY: 16px → 0, opacity: 0 → 1, scale: 0.97 → 1.0
```

---

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

---

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

---

## The Standard You Are Holding

When producing a Decision Room episode, ask yourself before each scene:

1. **Is this earning its screen time?** If a 10-second scene could be 6 seconds without losing
   anything, cut it to 6.

2. **Does this scene know what comes before and after it?** Every scene should feel like it was
   cut from the same roll as its neighbours.

3. **Would someone who has never heard of RestoreAssist understand the weight of this decision?**
   The audience is restoration professionals — they will feel the IICRC reference, the
   compliance burden, the field reality. Write to that.

4. **Is the motion serving the story or decorating it?** Animation that calls attention to
   itself has failed. The best motion is the kind the viewer doesn't consciously notice — they
   just feel the pacing is right.

5. **Could a 15-year editor defend every cut?** If you can't articulate why a transition
   happens at frame X rather than frame X+12, the transition is in the wrong place.

Read `references/timing-chart.md` for the full frame-by-frame beat map before writing any
composition code.
