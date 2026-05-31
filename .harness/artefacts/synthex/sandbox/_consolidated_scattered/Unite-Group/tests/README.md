# Synthex Test Suite

## Running Tests

```bash
# Run pipeline smoke tests (CI gate)
npm test

# Run all tests
npm run test:all
```

## Pipeline Smoke Tests

Located in `tests/pipelines/`. These tests block PR merge if they fail. There is no bypass mechanism.

| Test file | Pipeline | What it validates |
|---|---|---|
| `auto-calendar.smoke.test.ts` | Auto-Calendar | Calendar output has 7 slots, each with non-empty captions and valid ISO timestamps |
| `review-intelligence.smoke.test.ts` | Review Intelligence | Draft responses are non-empty strings > 20 chars, include reviewer name |
| `seasonal-engine.smoke.test.ts` | Seasonal Engine | Signals array is non-empty, each has opportunity_name and valid peak_date |

### Why these tests exist

These pipelines run against real client data and auto-publish without human review. The critical failure mode is a pipeline that returns HTTP 200 and writes a structurally correct but semantically empty row — a null `content` field, empty `draft_response`, or `seasonal_signals` of length 0. These failures are invisible to error monitoring and damage client content silently.

### Test Client Seed

The smoke tests use a synthetic test client: `smoke-test-client-trades-nsw`

For integration-mode tests (when a real Supabase dev environment is used), seed this client:

```sql
-- Seed test client for smoke tests
-- Run against Supabase dev environment only

INSERT INTO clients (id, business_name, industry, state, created_at)
VALUES (
  'smoke-test-client-trades-nsw',
  'Smoke Test Trades Business',
  'trades',
  'NSW',
  now()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO brand_profiles (client_id, brand_voice, tone, created_at)
VALUES (
  'smoke-test-client-trades-nsw',
  'professional',
  'helpful',
  now()
) ON CONFLICT (client_id) DO NOTHING;

-- Seed a GBP review for review-intelligence smoke test
INSERT INTO gbp_reviews (id, client_id, reviewer_name, rating, review_text, review_date)
VALUES (
  'rev-smoke-001',
  'smoke-test-client-trades-nsw',
  'Jane Smith',
  5,
  'Absolutely fantastic service. Highly recommend!',
  '2026-03-31'
) ON CONFLICT (id) DO NOTHING;
```

## Unit Tests

Located in `src/lib/**/*.test.ts`.

| Test file | What it tests |
|---|---|
| `src/lib/calendar/generateWeeklyCalendar.test.ts` | Weekly calendar orchestration (SYN-521) |
| `src/lib/notifications/detectFirstWin.test.ts` | First win detection logic |
| `src/lib/scoring/computeAuthorityScore.test.ts` | Authority score computation |
