# Decision Room: colour, typography and motion

Moved from SKILL.md. The visual tokens every scene shares.

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

Full hex values with interpolation keyframes: `color-system.md`

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

