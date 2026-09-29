---
name: nexus-viral
description: "Turn one idea into a hook-first 9:16 short-form video and repurpose it into 8 platform-native cuts, YouTube Shorts and Instagram Reels first, grounded in live trend and competitor intelligence. Reads trend signals and brand voice, never generates blind. Delegates hooks and captions to nexus-copywriter, generates through the Synthex video engine, and gates every publish through the Broadcast Grill. The YouTube cut carries the search metadata."
disable-model-invocation: false
allowed-tools: Read, Grep, Glob, Bash, WebFetch, WebSearch
---
# nexus-viral

Owns short-form virality: the hook, the retention shape, and the 1→8 repurpose. Never long-form (video-director owns YouTube episodes), never the words themselves (nexus-copywriter owns hooks/captions), never the raw provider call (the Synthex engine owns generation). This skill orchestrates those three and is accountable for one thing: nothing weak ships.

Reuse, don't rebuild. Every generation goes through the already-built Synthex engine (`lib/services/ai/video`), every gate through video-director, every word through nexus-copywriter. This skill adds the viral-specific intelligence, method cards, retention grading, and repurpose matrix — nothing that already exists.

## Triggers

- Brief mentions "viral", "short-form", "reel", "TikTok", "YouTube", "Shorts", "Instagram", "hook", "repurpose", "1→8", "short video", "UGC clip".
- Or invoked by `marketing-orchestrator` after positioning + ICP exist and the channel plan calls for short-form.

## Inputs

Mandatory upstream artifacts:
- `BrandConfig` (voice, forbiddenWords, tagline) + `brand_dna` row for the org
- `positioning.md` from `marketing-positioning`
- `icp/{slug}-{date}.md` from `marketing-icp-research`
- Live Nexus conventions — fetched from Pi-Dev-Ops at run time, never forked into this repo

Per-job:
- `topic` — what the short is about (or `auto` to pull the top-scored row from `video_topic_queue`)
- `platforms` — target set from the canonical Synthex platform ids: `youtube | instagram | tiktok | linkedin | x | facebook | pinterest | snapchat` (default: all eight → the 1→8 set; youtube publishes to the Shorts surface, instagram to Reels). **Money-maker doctrine: all roads lead to YouTube and Google/Bing** — the youtube cut is derived first and anchors the set with a search/keyword title, an indexable description, and tags (see `references/repurpose-matrix.md`); site embeds of the set point at the YouTube asset with `VideoObject` schema.
- `heroModel` (optional) — override the routed model; default lets the registry route (draft-first)
- `reference` (optional) — brand character still / product image for consistency across cuts

## Method

The run is four gated stages. Stage 2 spends nothing until Stage 1's Brief Grill clears; Stage 4 publishes nothing until Stage 3's Broadcast Grill clears.

### 1. Intelligence (scope before spend)
Pull trend + competitor signal through Apify (`references/intelligence.md`) and score it into `video_topic_queue`: hooks that are trending in-niche, competitor shorts that overperformed, comment-mined pains. Present the top-scored angle as the Brief. The Brief Grill (video-director Gate A) confirms scope, brand fit, and budget before any credit is spent — a vague or off-brand brief is bounced here, not after generation.

### 2. Hook + generate
- **Hook/caption → delegate to `nexus-copywriter`** (`artifact: ad-copy`, short cadence). It returns the ≤7-second spoken/text hook, the on-screen caption track, and the platform captions. nexus-viral never writes the words itself; it supplies the trend context and brand voice and consumes the copy.
- **Generate the hero short** through the Synthex engine: 9:16, hook-first, retention-shaped (`references/viral-playbook.md`). Routing prefers pre-paid Artlist over metered fal; draft-first unless the Brief approved premium. The method cards in `engine/cards/viral-method-cards.json` carry the viral shot grammar (pattern-interrupt open, 3-beat retention, loop-back close).

### 3. Broadcast Grill (quality before publish)
Every hero short passes the viral lenses in `references/broadcast-grill-viral.md` — an extension of video-director's Gate B: does the first frame stop the scroll, does the hook land in ≤2s, is retention shaped (no dead middle), are captions burned and legible muted, is the loop clean, is AI/synthetic media disclosed. A FAIL is terminal — it writes a `marketing_agency_qa_reports` row and stops. It does not self-approve.

### 4. Repurpose 1→8
Take the passed hero and derive the 8 platform-native cuts through the existing `lib/video/social-derivation` path plus the specs in `references/repurpose-matrix.md`: per-platform aspect/safe-zone, duration, caption placement, hashtag/sound conventions, and CTA. Each derived cut re-runs only the captions/safe-zone lenses (not a full regenerate). The set lands in `video_assets` and is enqueued to `publish_queue` — human-gated, never auto-posted.

## Voice enforcement

Hooks and captions are nexus-copywriter's output, so they inherit its filters: `BrandConfig.voice.forbiddenWords` (always blocks `we / our / I / us / my`), no AI filler (delve, tapestry, leverage, robust, seamless, elevate), brand cadence. nexus-viral adds one rule of its own: no fabricated virality — no invented view counts, fake duet/stitch credits, or "as seen on" claims. Trend framing must trace to a real signal row.

## Output

`<calling-project>/.marketing/viral/{jobId}/` — the hero plus the 8 cuts, each with structured frontmatter:
```yaml
---
artifact: viral-short
brand: synthex
job: synthex-viral-2026-07-10
topic: "3-second water-damage myth"
heroAssetId: video_assets/…
platform: tiktok
copywriterRef: ../copy/{jobId}/ad-copy.md
trendSignalRef: video_topic_queue/…
broadcastGrill: PASS
qaReportRef: marketing_agency_qa_reports/…
aiDisclosure: true
publishState: queued_human_gated
---
```

## Boundaries

- Never generate before the Brief Grill clears — scope-before-spend is non-negotiable.
- Never publish a cut that failed the Broadcast Grill, and never hardcode the grill result to PASS. The run does not self-approve; a FAIL is terminal for that asset.
- Never write the hook or captions inline — delegate to `nexus-copywriter`. If it's unavailable, emit a `BLOCKED` artifact rather than fabricate copy.
- Never rebuild what the Synthex engine already does (providers, cards, quota, publish queue) or what video-director already does (the two gates). Compose them.
- Never fork the Nexus Prompt into this repo — inherit it live from Pi-Dev-Ops.
- Never auto-post. Every cut lands in `publish_queue` for human release.
- Never invent virality signals, view counts, or social proof. Trend framing traces to a real `video_topic_queue` / competitor row or it doesn't ship.
- Never bypass the org quota or the MCP daily sub-cap; draft-first unless the Brief approved premium.

## Hands off to

- `nexus-copywriter` (upstream, per job: hooks + captions)
- `video-director` (shared gates; and any long-form/YouTube cut of the same topic)
- `marketing-launch-runbook` (slots the 8 cuts onto the posting calendar)
- `marketing-orchestrator` (reports the set + QA back to the campaign)

## Per-project keys

- `APIFY_API_TOKEN` — trend/competitor intelligence. Missing → Stage 1 runs on `video_topic_queue`/`tracked_competitors` only and flags reduced signal.
- `FAL_API_KEY` / Artlist plan — generation via the engine; Artlist pre-paid is preferred. Missing both → returns the Shot Brief and refuses to fabricate a render.
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — used by nexus-copywriter for the hook/caption pass, not by this skill directly.
