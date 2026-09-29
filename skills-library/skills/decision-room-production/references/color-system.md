# Decision Room — Colour System

## Per-Act Values

All interpolations use 15-frame cross-fades at act boundaries unless noted.

### Cold Open
```
background:  #0a0f1a
cyan:        #0891b2  opacity: 0.60
body text:   #9ca3af
```

### Act 1 — Problem
```
background:  #101827
cyan:        #06b6d4  opacity: 0.65
body text:   #d1d5db
headline:    #f4f5f6
```

### Act 2 — Methods
```
background:  #152338  (RestoreAssist base navy)
cyan:        #06b6d4  opacity: 1.00
body text:   #f4f5f6
code blocks: #0d1117 background, #06b6d4 left border
```

### Act 3 — SWOT (split-screen tension)

Left half (Strengths):
```
background:  #152338  with warm left gradient: rgba(251,191,36,0.04)
headline:    #fbbf24  (amber)
body text:   #f4f5f6
```

Right half (Weaknesses) — enters simultaneously from right:
```
background:  #1a1020  (cooler, slight purple)
headline:    #e879f9  (muted purple)
body text:   #e2e8f0
```

Rising (Opportunities):
```
background:  #0f2318
headline:    #34d399  (emerald)
body text:   #f4f5f6
```

Descending (Threats) — brief, do not dwell:
```
background:  #1a100f
headline:    #f87171  opacity: 0.80
body text:   #fca5a5
```

Mid-act neutral hold:
```
background:  #111827
all elements: at stated opacity values
```

### Act 4 — Decision Granted
```
background:  #1a1508  (warm dark — first warmth of the episode)
cyan:        #06b6d4  opacity: 1.00
decision text: #ffffff
"SHIPPED":   #06b6d4  opacity: 0.60
watermark:   #f4f5f6  opacity: 0.40
ticket ref:  #9ca3af  opacity: 0.55
```

### Act 5 — Product Alive
```
background:  #0f172a  (slate dark — neutral close)
cyan:        #06b6d4  opacity: 1.00
url text:    #f4f5f6
logo:        full opacity fading to 0.70
```

## Glow Orbs
Place 2–3 per scene. Positions shift per act to avoid static feel.

```tsx
// Problem act orbs
<GlowOrb x={1600} y={200} size={600} opacity={0.07} color={CYAN} />
<GlowOrb x={200}  y={700} size={400} opacity={0.05} color={CYAN} />

// SWOT strengths side orb
<GlowOrb x={480}  y={540} size={800} opacity={0.06} color="#fbbf24" />

// SWOT weaknesses side orb
<GlowOrb x={1440} y={540} size={800} opacity={0.05} color="#9333ea" />

// Decision Granted — warm centre orb
<GlowOrb x={960}  y={540} size={1200} opacity={0.10} color="#f59e0b" />
```

## Grid Overlay
Use on all acts. Opacity varies:
- Cold open: 0.06
- Problem: 0.08
- Methods: 0.10
- SWOT: 0.08
- Decision: 0.06
- Product: 0.04 (barely visible — product screens take priority)
