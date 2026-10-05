# Repurpose matrix — 1 hero → 8 platform-native cuts

The hero passes the grill once. Repurpose derives platform cuts through the existing
`lib/video/social-derivation` path — it does not regenerate. Each cut re-runs only the
captions + safe-zone lenses. The point is native fit, not eight identical re-uploads: a
Reel and a TikTok that look cross-posted both get suppressed.

## Money-maker doctrine

All roads lead to YouTube and Google/Bing. YouTube is the only destination in the set
whose cuts are durably **searchable** — Shorts rank in YouTube search and surface in
Google/Bing video results, so the YouTube cut is derived FIRST and is the anchor of the
set. Two consequences:

- The **YouTube cut carries search metadata**, not just a caption: a keyword title,
  a description written for Google/Bing indexing, and tags — attached to the
  `publish_queue` row. nexus-copywriter's youtube caption is that search package.
- Where the set is embedded on a site, the embed points at the YouTube asset and gets
  `VideoObject` schema via Synthex's `lib/video/schema-injector` path so Google/Bing
  index the page as a video result. Instagram is the second money-maker (reach +
  profile conversion); it follows YouTube in derivation order.

Platform ids below are **canonical Synthex platform ids** (what `publish_queue` and the
platform connectors speak). Reels and Shorts are surfaces of instagram/youtube, not ids.

| Platform (id) | Surface | Aspect / len | Caption + safe zone | Native conventions | CTA |
| --- | --- | --- | --- | --- | --- |
| youtube | Shorts | 9:16 · ≤60s | burned; title text overlaps hook | search/keyword title, Google/Bing-indexable description, tags, #Shorts, chapters off | subscribe seed |
| instagram | Reels | 9:16 · 7–15s | burned; clear right rail + bottom | trending audio, cover frame set, ≤1 hashtag block | "save this" |
| tiktok | feed | 9:16 · 7–15s | burned, upper-third; keep bottom 15% + right 12% clear | trending sound, on-screen text hook, duet/stitch-bait | comment prompt |
| linkedin | feed | 1:1 or 9:16 · 15–30s | burned; professional register | native upload, first-line hook in copy, no external link in body | DM / doc |
| x | feed | 1:1 or 16:9 · ≤30s | burned; short | native video, hook in first tweet line, thread the payoff | reply prompt |
| facebook | Reels | 9:16 · 7–20s | burned; large text | Reels surface, family-safe framing | share prompt |
| pinterest | idea pin | 9:16 · 6–15s | burned; text-heavy cover | keyword title + description (also search-indexed), idea-pin format | "get the guide" |
| snapchat | Spotlight | 9:16 · 5–10s | burned; centre-safe | Spotlight, fast open, no external UI | swipe prompt |

## Derivation rules

- **Never re-caption from scratch per platform** — take nexus-copywriter's platform caption
  set (it returned all eight) and place per the safe-zone column.
- **Aspect changes are crops, not regenerations** — 1:1/16:9 cuts crop the 9:16 hero with
  the focal subject kept centre; if a crop loses the subject, flag for a re-frame, don't ship.
- **Sound/hashtag conventions are metadata**, attached to the `publish_queue` row, not baked
  into the video (so the human can swap the trending sound at post time).
- **Duration trims** cut from the tail (keep the hook), never the open.
- Each cut lands in `video_assets` linked to the hero, and enqueues to `publish_queue` with
  `publishState: queued_human_gated`. No auto-post, ever.

## The 8th-platform rule

If the angle only travels to, say, five platforms (per the intelligence "repurpose reach"
score), derive five — don't pad to eight with cuts that don't fit. A forced Pinterest cut of
a talking-head rant is worse than no Pinterest cut.
