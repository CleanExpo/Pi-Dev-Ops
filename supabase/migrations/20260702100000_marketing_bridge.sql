-- UNI-2236 — marketing skill↔cron bridge queue tables.
-- Publisher crons (Unite-Hub) drain social_posts; Pi-CEO seeds rows via
-- swarm/marketing_skill_bridge.py after skill runs.

CREATE TABLE IF NOT EXISTS social_posts (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       TEXT        NOT NULL DEFAULT 'pi-ceo',
  business_key    TEXT        NOT NULL,
  content         TEXT        NOT NULL,
  title           TEXT,
  media_urls      TEXT[]      NOT NULL DEFAULT '{}',
  platforms       TEXT[]      NOT NULL DEFAULT '{}',
  status          TEXT        NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'scheduled', 'publishing', 'published', 'failed')),
  scheduled_at    TIMESTAMPTZ,
  platform_post_ids JSONB     NOT NULL DEFAULT '{}',
  error_message   TEXT,
  metadata        JSONB       NOT NULL DEFAULT '{}',
  eeat_score      JSONB,
  geo_score       JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS social_posts_status_scheduled_idx
  ON social_posts (status, scheduled_at)
  WHERE status IN ('draft', 'scheduled');

CREATE INDEX IF NOT EXISTS social_posts_business_key_idx
  ON social_posts (business_key, created_at DESC);
