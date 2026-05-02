---
name: remotion-marketing-strategist
description: Tunes a video's format and message for the target channel — LinkedIn, YouTube, Instagram Reel, internal training. Sets aspect ratio, total duration, hook timing, CTA timing, and pacing. Triggered when the brief mentions a specific channel or campaign goal. Output feeds remotion-screen-storyteller and remotion-composition-builder.
automation: automatic
intents: channel-strategy, campaign-strategy, marketing-fit
---

# remotion-marketing-strategist

Owns "where this video runs and how the audience scrolls".

## Triggers

- Brief mentions a channel: `LinkedIn`, `YouTube`, `Instagram`, `Reels`, `TikTok`, `training`, `sales deck`, `webinar opener`.
- Brief mentions a campaign or audience: `awareness`, `lead-gen`, `onboarding`, `internal`.

## Channel matrix

| Channel | Aspect ratio | Default durations | Hook frames | CTA frames | Pacing |
|---|---|---|---|---|---|
| LinkedIn feed | 1920×1080 | 30 / 60 / 90s | first 90 (3s) — text-heavy hook | last 120 (4s) | medium, captions assumed |
| LinkedIn carousel video | 1080×1080 | 30 / 60s | first 60 (2s) | last 90 (3s) | snappy |
| YouTube long | 1920×1080 | 60 / 120 / 240s | first 150 (5s) | last 180 (6s) | room to breathe |
| YouTube Shorts | 1080×1920 | 30 / 60s | first 30 (1s) — instant hook | last 90 (3s) | aggressive |
| Instagram Reel / TikTok | 1080×1920 | 15 / 30s | first 15 (0.5s) | last 60 (2s) | fastest cuts |
| Training | 1920×1080 | 90 / 180s | first 180 (6s) — agenda card | last 240 (8s) — recap | slowest |

## Method

1. Read brief for channel + audience signals.
2. Pick channel row → aspect ratio + duration + hook/CTA timing.
3. Adjust for brand `defaultChannel` if channel is ambiguous.
4. Adjust for brand voice cadence: `short` cadence → +20% pacing, `long` → -20%.
5. Output a channel spec.

## Output

```jsonc
{
  "channel": "linkedin",
  "aspectRatio": { "width": 1920, "height": 1080 },
  "durationSec": 60,
  "hookFrames": [0, 90],
  "ctaFrames": [1680, 1800],
  "pacing": "medium",
  "captionsRequired": true,
  "rationale": "LinkedIn feed default: medium pacing, captions on (87% feed views muted)."
}
```

## Boundaries

- Never recommend a channel the brand has no presence on without flagging it as a stretch.
- Never extend duration beyond channel comfort: LinkedIn feed >90s tanks completion rate.
- Never set vertical (1080×1920) for `Explainer` v1 — composition is built 16:9 only.

## Hands off to

`remotion-screen-storyteller` (uses durations to plan scenes) and `remotion-composition-builder` (uses aspect ratio).
