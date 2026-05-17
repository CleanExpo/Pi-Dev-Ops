---
brand: ra
job: ra-practitioner-story-series-2026-05-12
asset: Practitioner Story Series
surface: social
voice: klark-brown
primaryChannel: linkedin
crossChannel: [instagram-reels]
totalAssets: 7
voiceLintPass: true
videosDispatched: 1
---

# RestoreAssist — Practitioner Story Series

Six LinkedIn text posts + one 30-second vertical Reel storyboard, written in
klark-brown peer-instructor voice for ANZ restoration practitioners. Every post
features a real-feel field story where documentation discipline was the
difference between paid scope and lost scope. Each ends with a question
calibrated for IICRC-credentialled peers — not generic engagement bait.

## Posting Cadence

LinkedIn's sustainable cadence for technical B2B is 2–3 posts per week. Drop
across three weeks:

| Week | Mon | Wed | Fri |
|---|---|---|---|
| 1 | `linkedin-1.md` (Cairns scope dispute) | `linkedin-2.md` (Brisbane moisture map) | `linkedin-3.md` (Sydney Cat-3 reclassification) |
| 2 | `linkedin-4.md` (Bathroom→whole-house) | `video-1.storyboard.md` (Reel — variant of post 4) | `linkedin-5.md` (Mould containment cautionary) |
| 3 | `linkedin-6.md` (12 years on paper) | — | — |

The Reel runs as a standalone Wednesday slot in Week 2, native upload to
LinkedIn, cross-post to Instagram. It is variant content — not a duplicate of
post 4 — so the same narrative beats can land twice in the same week without
fatigue.

## Voice Audit

All seven assets verified against `ra.ts` `voice.forbiddenWords` and `doNot`:

- ✅ No leading `we` / `our` / `i` / `us` / `my`
- ✅ No `leverage`, `utilise`, `best-in-class`
- ✅ No AI-filler (`delve`, `tapestry`, `landscape`, `robust`, `seamless`)
- ✅ No "RA" abbreviation in any on-screen title or voiceover
- ✅ Red reserved for `colour.semantic.danger` only (one use, scene 3 of Reel)
- ✅ NIR / inspection standard never framed as optional or vendor-specific

## Story Map

| # | Story Archetype | Loss Type | Region | Teaching Beat |
|---|---|---|---|---|
| 1 | Scope dispute reversal | Cat-2 water | Cairns, QLD | Single stamped reading as evidence chain |
| 2 | Tear-out boundary defence | Cat-3 sewage | Brisbane, QLD | Moisture map as scope authority |
| 3 | Category reclassification refused | Cat-3 sewage | Sydney, NSW | S500 classification at time of arrival |
| 4 | Scope expansion held | Cat-2 water | (regional) | Continuous record vs retroactive notes |
| 5 | Cautionary — missing evidence | Cat-3 mould | Newcastle, NSW | Visual evidence ≠ written note (S520) |
| 6 | Transition story | Cat-2 water | Perth, WA | Same workflow, evidenced |
| 7 | Video variant of #4 | Cat-2 water | (regional) | Same beats in 30s vertical |

## Production Files

```
.marketing/social/ra-practitioner-story-series-2026-05-12/
├── INDEX.md                  ← you are here
├── linkedin-1.md             ← Cairns scope dispute ($48k saved)
├── linkedin-2.md             ← Brisbane moisture map
├── linkedin-3.md             ← Sydney Cat-3 reclassification
├── linkedin-4.md             ← Bathroom→whole-house ($7.8k → $47k)
├── linkedin-5.md             ← Newcastle mould containment (cautionary)
├── linkedin-6.md             ← Perth 12-year-vet first digital loss
└── video-1.storyboard.md     ← 30s vertical Reel + dispatch payload
```

## Downstream Hands-Off

- **`remotion-orchestrator`** — dispatch payload at the tail of
  `video-1.storyboard.md`. Composition id `practitioner-story-04`, brand `ra`,
  1080×1920, 30s, sweep signature motion, ElevenLabs Sarah AU narration.
- **`marketing-launch-runbook`** — slot all six text posts + the Reel into the
  three-week cadence above as the storytelling pillar of the launch calendar.
- **`marketing-analytics-attribution`** — per-post UTM. Suggested scheme:
  `utm_source=linkedin&utm_medium=social&utm_campaign=practitioner-story-2026-05&utm_content=story-{1..6}`,
  Reel `utm_content=story-04-reel`.

## Voice Reference — "klark-brown"

Peer-instructor cadence anchored in IICRC S500/S520 language. Direct, evidence-led,
no hype. Numbers always specific, never rounded for effect. Reads as a
trade-journal field report — not a brand campaign. Field techs see a peer
talking, not a marketer talking at them.
