# Intelligence — trend + competitor signal into the topic queue

Stage 1 fills `video_topic_queue` with scored angles so the Brief is grounded in a real
signal, not a guess. It reuses the same Apify actors as video-director's pre-fill; the
difference is the scoring, which is tuned for short-form velocity, not evergreen authority.

## Sources (Apify → tables)

- `streamers/youtube-scraper` + `pintostudio/youtube-transcript-scraper` — Shorts in-niche:
  what hooks are overperforming this week. → `video_topic_queue`
- `clockworks/tiktok-scraper` (or the account/hashtag variant) — trending sounds, formats,
  and hooks on TikTok for the niche. → `video_topic_queue`, sound refs → notes
- `apify/instagram-scraper` — Reels velocity and format patterns. → `video_topic_queue`
- `harshmaur/reddit-scraper` + youtube-comments-scraper — comment-mined pains and the
  exact phrasing real people use (feeds nexus-copywriter's hook). → `content_topic_suggestions`
- `tracked_competitors` (existing rows) — competitor shorts that broke out; reverse the hook.

If `APIFY_API_TOKEN` is absent, Stage 1 runs on existing `video_topic_queue`,
`tracked_competitors`, and `content_topic_suggestions` rows only and flags reduced signal
on the Brief.

## Scoring (short-form velocity)

Score each candidate 0–100 and write it to the queue row. Weight for velocity over volume:

- **Freshness** (0–30) — how recently the format/sound started trending; decays fast.
- **Fit** (0–25) — match to brand positioning + ICP vocabulary; off-brand trends score low
  even if hot (a viral cut that doesn't convert is a vanity metric).
- **Hookability** (0–25) — can it be a ≤2s hook with a real curiosity gap or stake.
- **Repurpose reach** (0–20) — how many of the 8 platforms the angle plausibly travels to.

The Brief presents the top-scored row. The human (or the calling agent) can override, but
the score and its inputs are shown so the choice is informed, not blind.

## Governance

- Read-only intelligence. This stage never writes outside `video_topic_queue` /
  `content_topic_suggestions` and never touches production data via `execute_sql`.
- Trends are signals, not scripts. The score justifies picking an angle; the hook itself
  still comes from nexus-copywriter and still passes voice enforcement.
- No scraping of private/gated content; public signal only, consistent with the campaign
  evidence rules.
