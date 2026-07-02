-- UNI-2236 — Pi-CEO marketing bridge columns on unite-group social_posts.
-- Base table is owned by unite-group (founder_id UUID, JSONB platforms/media_urls).
-- Pi-CEO seeds rows via swarm/marketing_skill_bridge.py; Unite-Hub
-- /api/cron/social-publisher drains scheduled rows.

ALTER TABLE public.social_posts
  ADD COLUMN IF NOT EXISTS metadata    JSONB,
  ADD COLUMN IF NOT EXISTS eeat_score  JSONB,
  ADD COLUMN IF NOT EXISTS geo_score   JSONB;

-- Backfill metadata default for existing rows
UPDATE public.social_posts
SET metadata = '{}'::jsonb
WHERE metadata IS NULL;

ALTER TABLE public.social_posts
  ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS social_posts_status_scheduled_idx
  ON public.social_posts (status, scheduled_at)
  WHERE status IN ('draft', 'scheduled');

CREATE INDEX IF NOT EXISTS social_posts_bridge_tenant_idx
  ON public.social_posts (business_key, created_at DESC);
