# Auto-Publish Failure Mode Register

**SYN-538 / SYN-523** | Sprint 3 | Owned by: Lead developer + Phill review

This register enumerates every runtime failure state the 48-hour auto-publish system (SYN-523) must handle before ship. It is an acceptance criterion: **any SYN-523 PR without a code path for each state below will be rejected in review.**

Session 6 answered "when does auto-publish activate?" (shadow mode, cold-start gate, 48-hour window). This document answers "what happens when auto-publish is active and something breaks?"

---

## How to Use This Register

For each failure mode:
- **Detection**: how the system knows it has occurred
- **Response**: what the system does immediately
- **User-visible impact**: what the client experiences
- **Escalation**: when a human is notified

---

## FM-001 — Expired Social Credentials

**Trigger**: Platform API returns 401/403 during post publish attempt.

**Detection**: HTTP 401 or 403 response from Instagram Graph API, Google My Business API, or any connected platform.

**Response**:
1. Abort publish attempt immediately — do not retry with expired credentials
2. Mark the `calendar_posts` row status as `credential_expired` (not `failed`)
3. Set `autopilot_runs.status = 'paused'` for this client
4. Queue a credential refresh notification to the client's registered email
5. Do NOT publish any subsequent scheduled posts until credentials are refreshed

**User-visible impact**: Post not published. Client receives email: "Your [Platform] connection needs to be refreshed — [link to reconnect]."

**Escalation**: If credentials are not refreshed within 48 hours, notify Phill via Slack #synthex-alerts.

**Test coverage required**: Mock 401 response from platform client, assert `credential_expired` status, assert no subsequent posts attempted.

---

## FM-002 — Platform Rate Limit (HTTP 429)

**Trigger**: Platform API returns 429 Too Many Requests.

**Detection**: HTTP 429 response, or platform-specific rate limit indicator in response body.

**Response**:
1. Parse `Retry-After` header if present; else use exponential backoff: 60s, 120s, 240s
2. Retry up to 3 times within the same calendar slot's publish window
3. If all 3 retries exhausted, mark post as `rate_limited_failed`
4. Log rate limit event to `autopilot_runs` with retry timestamps
5. Do NOT immediately retry the next scheduled post — honour the backoff window

**User-visible impact**: Post may be delayed by up to 8 minutes. If ultimately failed: post marked as `rate_limited_failed` in dashboard.

**Escalation**: If rate limiting persists across more than 3 consecutive posts for the same client, create a Slack alert — possible API quota issue at account level.

**Test coverage required**: Mock 429 with Retry-After header, assert retry count, assert exponential backoff timing, assert `rate_limited_failed` after 3 failures.

---

## FM-003 — Partial Post Failure with Retry Exhaustion

**Trigger**: Platform API accepts the request but returns an error for specific media (image resize failure, video format rejection, caption length limit exceeded).

**Detection**: HTTP 200 response with `error` field in platform response body (common in Instagram Graph API), or platform-specific partial failure indicators.

**Response**:
1. Parse platform error code from response body
2. Map to human-readable reason: `CAPTION_TOO_LONG`, `MEDIA_FORMAT_REJECTED`, `HASHTAG_BLOCKED`
3. Mark `calendar_posts.publish_error_code` with the mapped reason
4. Mark post as `partial_failure` — do NOT retry without human correction
5. Notify client dashboard: "Post could not be published: [reason]"

**User-visible impact**: Post visible in dashboard with specific error reason and suggested fix. Client can edit and re-queue.

**Escalation**: No immediate escalation. If `partial_failure` rate for a client exceeds 20% over 7 days, flag in weekly health check.

**Test coverage required**: Mock platform partial failure response, assert correct error code mapping, assert `partial_failure` status, assert no automatic retry.

---

## FM-004 — Client Account Deactivated

**Trigger**: Client record `is_active = false` or `autopilot_enabled = false` at time of publish attempt.

**Detection**: Pre-publish check against `clients` table before each post attempt.

**Response**:
1. Pre-publish check runs before any API call — zero external requests if client is inactive
2. Mark all pending `calendar_posts` as `skipped_account_inactive`
3. Mark `autopilot_runs.status = 'skipped'` with reason `account_deactivated`
4. Log the event for billing/audit purposes

**User-visible impact**: No posts published. No client notification (they deactivated — they know).

**Escalation**: None. This is expected behaviour.

**Test coverage required**: Assert zero platform API calls when client `is_active = false`. Assert all pending posts marked `skipped_account_inactive`.

---

## FM-005 — Content Freshness Validation Failure

**Trigger**: A `calendar_posts` row has `content = null`, `content = ''`, or `content` contains only whitespace/punctuation at publish time.

**Detection**: Pre-publish validation step checks `content.trim().length > 0` before any API call.

**Response**:
1. Pre-publish validation runs before any API call — zero external requests if content is empty
2. Mark post as `content_validation_failed` — do NOT publish empty content
3. Log validation failure with `calendar_posts.id` and timestamp
4. Do NOT advance to the next post — human review required for this client's queue

**User-visible impact**: Post not published. Dashboard shows warning: "Post requires review — content was empty when scheduled."

**Escalation**: Immediate Slack alert to #synthex-alerts. An empty content post reaching pre-publish validation is a pipeline bug (the CI smoke tests in SYN-590 should have caught this). Treat as P1.

**Test coverage required**: Assert zero platform API calls when `content` is null/empty/whitespace. Assert `content_validation_failed` status. Assert Slack alert is triggered.

---

## FM-006 — Supabase Write Failure (Post Status Update)

**Trigger**: After a successful platform post, the `UPDATE calendar_posts SET status = 'published'` call to Supabase fails.

**Detection**: Supabase client returns error on status update.

**Response**:
1. Log the Supabase write failure with the platform post ID (so it can be reconciled later)
2. Do NOT re-publish to the platform — the post already went live
3. Queue a Supabase retry (up to 3 attempts, 5s apart)
4. If retry exhaustion: write to local fallback log (`/tmp/synthex-reconcile.jsonl`) with post ID

**User-visible impact**: Post may appear as `publishing` in dashboard instead of `published` until reconciled. Cosmetic only — the post is live on the platform.

**Escalation**: If reconcile log has entries older than 1 hour, Slack alert to #synthex-alerts.

**Test coverage required**: Mock Supabase write failure after successful platform post. Assert no double-publish attempt. Assert reconcile log entry created.

---

## FM-007 — Anthropic API Failure During Caption Generation

**Trigger**: Caption generation (Claude Haiku call) fails during pre-scheduled content generation, not at publish time.

**Detection**: Anthropic API returns 5xx, timeout, or rate limit during `generateCaptions()`.

**Response**:
1. This failure occurs during calendar generation, not during publish — the post is never scheduled
2. Mark `calendar_posts` slot as `caption_generation_failed`
3. Retry with exponential backoff: 30s, 60s, 120s (max 3 retries)
4. If all retries fail: mark the slot as `needs_human_caption` — a human can provide content
5. Continue generating other slots — do not abort the entire calendar

**User-visible impact**: One or more calendar slots show "Needs your input" in dashboard.

**Escalation**: If more than 3 consecutive slots fail caption generation, the Anthropic API may be down. Alert #synthex-alerts.

**Test coverage required**: Mock Anthropic API 5xx. Assert slot marked `needs_human_caption`. Assert other slots generated successfully.

---

## FM-008 — Publish Window Expiry

**Trigger**: A post's `scheduled_for` timestamp is more than 4 hours in the past when the publish runner picks it up (e.g. the cron job was down).

**Detection**: Pre-publish check: `NOW() - scheduled_for > 4 hours`.

**Response**:
1. Mark post as `window_expired` — do NOT publish stale content
2. Log the expiry with gap duration
3. Do not reschedule automatically — content may be time-sensitive (e.g. "Happy Monday!")

**User-visible impact**: Post marked `expired` in dashboard. Client can re-queue if still relevant.

**Escalation**: If more than 5 posts expire in a single client's queue within 24 hours, the cron runner may have been down. Alert #synthex-alerts.

---

## Failure Mode Status Enum

All `calendar_posts.status` values that represent failure modes:

| Status | Meaning |
|--------|---------|
| `credential_expired` | FM-001: Platform credentials need refresh |
| `rate_limited_failed` | FM-002: Rate limit retries exhausted |
| `partial_failure` | FM-003: Platform accepted but returned error |
| `skipped_account_inactive` | FM-004: Client account deactivated |
| `content_validation_failed` | FM-005: Empty/null content at publish time |
| `caption_generation_failed` | FM-007: Anthropic API failure during generation |
| `needs_human_caption` | FM-007: Caption generation failed, human required |
| `window_expired` | FM-008: Publish window passed |

---

## What Changed This Decision

Per SYN-538 board memo: if auto-publish is moved from fallback to opt-in default during Sprint 3, this register must be reviewed and the scope of FM-004 and FM-008 expands to cover clients who never explicitly opted in.

---

*SYN-538 | Board Session 9 | 2026-03-30*
