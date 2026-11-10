---
name: decision-room-production
description: Produces RestoreAssist Decision Room episodes as cinematic Remotion compositions at senior production house quality. Use whenever writing, designing or rendering any Decision Room episode. Covers cold open philosophy, frame-precise timing charts, per-act colour grading, kinetic typography, the heartbeat emotional arc, the real asset pipeline (Playwright screenshots, code reveals, Linear ticket citations), sound design cues and the Remotion TSX patterns that encode them.
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

Do NOT produce generic bullet-card output. Every frame must be intentional.

Act temperature at a glance: cold open black and silent; Problem cold navy; Methods neutral, one
screen per method; SWOT in flux, a four-beat kinetic sequence not a 2x2 grid; Decision warm, one
sentence full bleed; Product alive, real screenshots then black and the RestoreAssist mark.

## Detail files (read the one for the stage you are on)

- [`references/timing-chart.md`](references/timing-chart.md) - read before writing any composition code: frame-by-frame beat map of each act.
- [`references/color-system.md`](references/color-system.md) - read when grading an act: full hex values and interpolation keyframes.
- [`references/act-philosophy.md`](references/act-philosophy.md) - read when writing or reviewing the content of any act, cold open to product alive.
- [`references/visual-system.md`](references/visual-system.md) - read when setting colours, typography or motion curves in TSX.
- [`references/heartbeat-assets-and-sound.md`](references/heartbeat-assets-and-sound.md) - read when pacing the emotional arc, sourcing screenshots, code reveals or ticket citations, or writing the voiceover pause cues.
- [`references/composition-and-schema.md`](references/composition-and-schema.md) - read when creating scene files or the episode JSON.

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
