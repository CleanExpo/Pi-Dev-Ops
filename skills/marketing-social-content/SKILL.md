---
name: marketing-social-content
description: Writes short-form social content — LinkedIn posts, X/Twitter threads, Instagram captions, TikTok hooks — and dispatches video shorts to remotion-orchestrator. Use when a brief asks for "social post", "LinkedIn post", "thread", "tweet", "Reels caption", "social campaign", "social calendar". Reads positioning + ICP vocabulary + channel-plan; cross-pack composes with remotion-orchestrator for any video output.
automation: automatic
intents: social-content, social-post, linkedin-post, twitter-thread, x-thread, instagram-caption, tiktok-hook, reels, social-calendar, short-form
---

# marketing-social-content

Owns short-form text for social. For social VIDEO, this skill writes the script + caption and **dispatches to `remotion-orchestrator`** — it does not author video itself.

## Triggers

- Brief mentions "LinkedIn post", "tweet", "X post", "thread", "Reels", "TikTok", "social post", "Instagram caption", "social calendar".
- Or invoked by `marketing-orchestrator` / `marketing-channel-strategist` for any short-form deliverable.
- Or by `marketing-copywriter` to atomise a long-form piece into social drops.

## Inputs

- `brand` slug
- `channels` — subset of `linkedin` / `x` / `instagram` / `tiktok` / `youtube-shorts` / `threads`
- `topic` or upstream `positioning.md` + `icp` doc
- `quantity` per channel
- `cadence` — single post / thread / week-long calendar
- `assetType` per slot — `text` / `carousel` / `video` / `image-quote`

## Method

### LinkedIn post (text)
- Hook line (≤8 words, specific number / contrarian claim / vivid image — never a generic "Excited to share…")
- 2-4 short paragraphs, ≤2 lines each (LinkedIn truncates after ~3 lines on mobile).
- One concrete example or stat per post.
- Closing line that invites a response (specific question, not "thoughts?").
- 0-3 hashtags max, all hyper-specific (no `#marketing #leadership`).
- No "We"/"Our"/"I" leading (Pi-CEO content rule).

### LinkedIn carousel
- Slide 1: hook + promise of payoff.
- Slides 2-9: one idea per slide, ≤15 words.
- Slide 10: CTA (next post / link / DM).
- Caption: 2-line teaser + "Carousel below ↓".

### X / Twitter thread
- Tweet 1: hook (specific, fits in preview).
- Tweets 2-N: one idea per tweet, max 7-10 tweets.
- Last tweet: CTA + bookmark prompt.
- No emoji clutter; one per tweet max if any.

### Instagram / TikTok video (caption + dispatch)
- Caption: ≤125 chars (above the "more" fold).
- Hashtag block: 5-10, mix high-volume + niche.
- Script for the video → DISPATCH to `remotion-orchestrator` with:
  - `composition`: `SocialAd` (vertical 1080×1920) — built in Remotion v1.1; falls back to `Explainer` 16:9 in v1 with note.
  - `durationSec`: 15 / 30 / 60.
  - `storyboard` derived from the script.
  - `brand`: same slug.

### Image quote / static graphic
- Quote text (≤14 words).
- Attribution.
- Visual brief for the designer (calling out `BrandConfig.colour.primary` + typography display family) — passes to `remotion-designer` if design-pass is wanted, or stays as a brief for an external designer.

## Output

`<calling-project>/.marketing/social/{jobId}/{channel}-{n}.md`:

```yaml
---
channel: linkedin
brand: synthex
job: synthex-launch-2026-04-28
slot: 3-of-12
assetType: text
hashtags: [SyntheticData, MLOps, AISafety]
voiceLintPass: true
videoDispatched: false
---
```

For video slots, output includes `videoDispatched: true` with the `remotion-orchestrator` job ID it created.

## Boundaries

- Never lead with "We" / "Our" / "I" — global Pi-CEO content rule.
- Never use AI-filler words (delve, tapestry, leverage, robust, seamless).
- Never recommend posting frequency above the brand's sustainable cadence (set by `marketing-channel-strategist`).
- Never DIY video — always dispatch to `remotion-orchestrator`.
- Never write engagement-bait CTAs ("comment YES if you agree") for B2B brands — voice mismatch.

## Hands off to

- `remotion-orchestrator` (cross-pack: every video slot dispatches here)
- `marketing-launch-runbook` (slots social drops onto launch calendar)
- `marketing-analytics-attribution` (per-post UTM)

## Per-project keys

- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — drafting + hook variant generation. Missing → returns the brief structure with "fill the hook" placeholders.
- No social-platform API keys required for v1 — outputs are drafts, the user / scheduler posts them. Future v1.1: `BUFFER_API_KEY` / `LINKEDIN_*` for direct scheduling.
