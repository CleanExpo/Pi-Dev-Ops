# Decision Room: act philosophy

Moved from SKILL.md. Per-act intent, copy rules and colour temperature.

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

Final frame: black. RestoreAssist mark. `restoreassist.app`. Nothing else.

