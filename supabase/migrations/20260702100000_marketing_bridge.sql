-- UNI-2236 — social_posts queue for marketing skill↔cron bridge.
-- Pi-CEO seeds rows (swarm/marketing_skill_bridge.py); Unite-Hub
-- /api/cron/social-publisher drains scheduled rows.
--
-- Idempotent: safe on empty Pi-Dev-Ops DB (CREATE) and unite-group DB (ALTER add cols).

CREATE TABLE IF NOT EXISTS public.social_posts (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  founder_id          UUID        NOT NULL,
  business_key        TEXT        NOT NULL,
  title               TEXT,
  content             TEXT        NOT NULL,
  media_urls          JSONB       NOT NULL DEFAULT '[]'::jsonb,
  platforms           JSONB       NOT NULL DEFAULT '[]'::jsonb,
  status              TEXT        NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'scheduled', 'publishing', 'published', 'failed')),
  scheduled_at        TIMESTAMPTZ,
  published_at        TIMESTAMPTZ,
  platform_post_ids   JSONB       NOT NULL DEFAULT '{}'::jsonb,
  error_message       TEXT,
  metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb,
  eeat_score          JSONB,
  geo_score           JSONB,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bridge columns on pre-existing unite-group tables (CREATE IF NOT EXISTS skips when present)
ALTER TABLE public.social_posts
  ADD COLUMN IF NOT EXISTS metadata    JSONB,
  ADD COLUMN IF NOT EXISTS eeat_score  JSONB,
  ADD COLUMN IF NOT EXISTS geo_score   JSONB;

UPDATE public.social_posts
SET metadata = '{}'::jsonb
WHERE metadata IS NULL;

ALTER TABLE public.social_posts
  ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;

ALTER TABLE public.social_posts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "social_posts_service_role" ON public.social_posts;
CREATE POLICY "social_posts_service_role"
  ON public.social_posts FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE INDEX IF NOT EXISTS social_posts_status_scheduled_idx
  ON public.social_posts (status, scheduled_at)
  WHERE status IN ('draft', 'scheduled');

CREATE INDEX IF NOT EXISTS social_posts_business_key_idx
  ON public.social_posts (business_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_posts_founder
  ON public.social_posts (founder_id);
