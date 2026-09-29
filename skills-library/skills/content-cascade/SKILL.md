---
name: content-cascade
description: Repurpose one published video into written formats — type /content-cascade <video URL or brand channel> to turn its transcript into a blog post, LinkedIn post, and X post in the brand voice, gated through nexus-copywriter. Drafts only; publish stays founder-gated.
argument-hint: "<YouTube URL, or brand name to check its channel for new uploads>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write, Agent, WebSearch, WebFetch, Skill
---

# content-cascade — one video, three written formats, one voice

A published video is the estate's most expensive content unit; this skill amortises it into
a blog post, a LinkedIn post, and an X post — each format-native, each in the brand's voice,
each gated. Cascade direction is video→writing; it never generates video.

## When to invoke

- A video just published on a brand channel (RA, CARSI, Unite, Synthex, DR/NRPG) and no
  written derivatives exist yet.
- Periodic check: "did <brand> publish anything new that hasn't cascaded?"
- You are about to write a from-scratch blog/social post on a topic an existing video
  already covers — stop, cascade the video instead.

## Core procedure

1. **Resolve the video.** From a URL, proceed. From a brand name, check the channel for
   uploads newer than the last cascade (record kept in the output folder's `index.md`).
   Nothing new → report "no new uploads" and stop.
   - Done when: one target video with title, URL, publish date.
2. **Fetch the transcript** (`yt-dlp` auto-subs, or the YouTube API plane from
   `library/connections.md`). No transcript retrievable → STOP and report; never
   reconstruct content from the title or thumbnail.
   - Done when: full transcript text in hand.
3. **Load the voice.** Read the brand's persona charter from vault `Personas/` and prior
   published examples of the SAME format. No persona charter → flag it, use
   `nexus-copywriter` defaults, and note the gap in the output.
   - Done when: voice constraints named per format (blog ≠ LinkedIn ≠ X).
4. **Draft three formats** through `nexus-copywriter` (the estate content gate — every
   claim sourced to a transcript timestamp or a real citation, active-voice CTAs):
   - **Blog** (600-1200 words): standalone value + embedded video; the transcript's
     argument restructured for reading, never a transcript dump.
   - **LinkedIn** (≤1300 chars): one insight from the video, native tone, link in comments
     convention.
   - **X** (single post or ≤5-post thread): the sharpest single claim, link on the last post.
   - Done when: three drafts pass the nexus-copywriter self-audit.
5. **Package for review.** Write drafts + metadata to the output folder (below) and surface
   for founder approval. Publishing is a separate, human-triggered act.
   - Done when: folder complete; reply names it and states PUBLISH IS NOT DONE.

## Output format

`~/2nd Brain/2nd Brain/Briefs/YYYY-MM-DD-cascade-<brand>-<slug>/` containing `blog.md`,
`linkedin.md`, `x.md`, and `meta.md` (video URL, publish date, voice sources used, claims→
timestamp map). Update the folder's `index.md` line recording the cascade (this is the
"last cascade" pointer step 1 reads).

## Calibration

- Full run ≤ 20 minutes. Blog 600-1200 words; shorter is a LinkedIn post, longer is a
  rewrite nobody asked for.
- One video per invocation. A backlog of uncascaded videos = run it N times, newest first.

## What this skill is NOT

- Not `nexus-viral` — that goes idea→video→8 video cuts; this goes published-video→writing.
- Not `brand-video` / `video-director` — no video is generated here, ever.
- Not `marketing-social-content` — that writes social from a campaign brief; this derives
  strictly from an existing video's transcript.
- Not a publisher — no posting, scheduling, or upload. Founder-gated, always.

## Hard rules

1. Words ship through `nexus-copywriter` then `brand-guardian` — the cascade never bypasses
   the estate content gate.
2. Never fabricate from title/thumbnail when the transcript fails — fabricated derivatives
   are the worst-case violation of the no-false-recordings directive.
3. Drafts only. The reply must state explicitly that nothing was published.
4. Voice is per-brand AND per-format; one generic rewrite×3 is the observed naive failure.
   Calibrate voice the destruction-cycle way: human eviscerates drafts, skill notes update —
   there is no one-shot self-improving voice (source's explicit warning).

## Provenance

- Source: Chase AI personal-assistant system — https://www.youtube.com/watch?v=gUv7VqcRzok
- Vault: `Wiki/claude-personal-assistant-system-2026-07-15-ingest.md` (cascade design,
  voice destruction-cycle method).
