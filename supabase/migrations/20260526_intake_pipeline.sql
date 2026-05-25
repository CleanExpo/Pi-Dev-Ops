-- Migration: Client Intake Pipeline — Phase 1 (CIP-PR1).
--
-- 5 tables backing the per-client Telegram → Margot → SPM → Board pipeline:
--   - intake_client_bots          (one row per client's Telegram bot)
--   - intake_threads              (one ongoing project conversation)
--   - intake_messages             (each inbound + outbound message)
--   - intake_board_rounds         (each board fan-out for a thread)
--   - intake_production_handoffs  (final exit: branch + PR + Linear)
--
-- All tables are tenant-scoped via `client_slug` + the existing
-- `set_app_tenant(slug)` RLS function from
-- 20260515_pilot_v1_phase1.sql. Duncan never sees Toby's data.
--
-- Apply with the Supabase MCP `apply_migration` tool, NOT
-- `supabase db query --linked -f` (the CLI's JSON-wrapping breaks on
-- DO blocks per unite-group-ci-recovery skill §3.1).
--
-- See swarm/intake/SPEC.md for full design.

-- ============================================================
-- intake_client_bots — per-client Telegram bot config
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_client_bots (
  id                  TEXT        PRIMARY KEY,
  client_slug         TEXT        NOT NULL,
  display_name        TEXT        NOT NULL,
  bot_username        TEXT        NOT NULL UNIQUE,
  bot_token_env_name  TEXT        NOT NULL,
  linear_team_id      TEXT        NOT NULL,
  linear_project_id   TEXT,
  github_repo         TEXT        NOT NULL,
  authorized_chat_ids TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
  long_poll_offset    BIGINT      NOT NULL DEFAULT 0,
  greeting_template   TEXT,
  max_board_rounds    INTEGER     NOT NULL DEFAULT 3,
  status              TEXT        NOT NULL DEFAULT 'active',
  config              JSONB,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT intake_client_bots_status_check
    CHECK (status IN ('active', 'paused', 'archived')),
  CONSTRAINT intake_client_bots_rounds_check
    CHECK (max_board_rounds BETWEEN 1 AND 20)
);

CREATE UNIQUE INDEX IF NOT EXISTS intake_client_bots_client_slug_uniq
  ON public.intake_client_bots (client_slug);
CREATE INDEX IF NOT EXISTS intake_client_bots_status_idx
  ON public.intake_client_bots (status);

-- ============================================================
-- intake_threads — one ongoing project conversation
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_threads (
  id                    TEXT        PRIMARY KEY,
  client_bot_id         TEXT        NOT NULL,
  client_slug           TEXT        NOT NULL,
  chat_id               TEXT        NOT NULL,
  title                 TEXT,
  status                TEXT        NOT NULL DEFAULT 'open',
  spm_assessment        JSONB,
  board_rounds          INTEGER     NOT NULL DEFAULT 0,
  last_message_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  production_handoff_id TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT intake_threads_status_check
    CHECK (status IN ('open', 'in_board', 'awaiting_client', 'ready_for_production', 'shipped', 'cancelled', 'paused_human_review')),
  CONSTRAINT intake_threads_client_bot_id_fkey
    FOREIGN KEY (client_bot_id) REFERENCES public.intake_client_bots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS intake_threads_client_status_idx
  ON public.intake_threads (client_slug, status);
CREATE INDEX IF NOT EXISTS intake_threads_chat_idx
  ON public.intake_threads (chat_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS intake_threads_bot_idx
  ON public.intake_threads (client_bot_id);

-- ============================================================
-- intake_messages — each inbound + outbound message
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_messages (
  id                    TEXT        PRIMARY KEY,
  thread_id             TEXT        NOT NULL,
  client_slug           TEXT        NOT NULL,
  direction             TEXT        NOT NULL,
  telegram_message_id   BIGINT,
  telegram_update_id    BIGINT,
  author                TEXT        NOT NULL,
  body                  TEXT        NOT NULL,
  metadata              JSONB,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT intake_messages_direction_check
    CHECK (direction IN ('inbound', 'outbound')),
  CONSTRAINT intake_messages_author_check
    CHECK (author IN ('client', 'margot', 'spm', 'board-summary', 'system')),
  CONSTRAINT intake_messages_thread_id_fkey
    FOREIGN KEY (thread_id) REFERENCES public.intake_threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS intake_messages_thread_created_idx
  ON public.intake_messages (thread_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS intake_messages_update_uniq
  ON public.intake_messages (client_slug, telegram_update_id)
  WHERE telegram_update_id IS NOT NULL;

-- ============================================================
-- intake_board_rounds — each board fan-out for a thread
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_board_rounds (
  id                  TEXT        PRIMARY KEY,
  thread_id           TEXT        NOT NULL,
  client_slug         TEXT        NOT NULL,
  round_number        INTEGER     NOT NULL,
  spm_brief           JSONB       NOT NULL,
  board_session_id    TEXT,
  minutes_path        TEXT,
  aggregated_reply    TEXT,
  status              TEXT        NOT NULL DEFAULT 'requested',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at        TIMESTAMPTZ,
  CONSTRAINT intake_board_rounds_status_check
    CHECK (status IN ('requested', 'deliberating', 'aggregated', 'replied', 'failed')),
  CONSTRAINT intake_board_rounds_thread_id_fkey
    FOREIGN KEY (thread_id) REFERENCES public.intake_threads(id) ON DELETE CASCADE,
  CONSTRAINT intake_board_rounds_round_unique
    UNIQUE (thread_id, round_number),
  CONSTRAINT intake_board_rounds_round_positive
    CHECK (round_number >= 1)
);

CREATE INDEX IF NOT EXISTS intake_board_rounds_thread_idx
  ON public.intake_board_rounds (thread_id, round_number);
CREATE INDEX IF NOT EXISTS intake_board_rounds_status_idx
  ON public.intake_board_rounds (client_slug, status);

-- ============================================================
-- intake_production_handoffs — final exit artifact
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_production_handoffs (
  id                  TEXT        PRIMARY KEY,
  thread_id           TEXT        NOT NULL UNIQUE,
  client_slug         TEXT        NOT NULL,
  github_repo         TEXT        NOT NULL,
  github_branch       TEXT        NOT NULL,
  github_pr_url       TEXT,
  linear_team_id      TEXT        NOT NULL,
  linear_project_id   TEXT,
  linear_issue_id     TEXT,
  linear_issue_url    TEXT,
  status              TEXT        NOT NULL DEFAULT 'pending',
  error_message       TEXT,
  shipped_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT intake_production_handoffs_status_check
    CHECK (status IN ('pending', 'repo_branched', 'pr_opened', 'linear_created', 'notified', 'complete', 'failed')),
  CONSTRAINT intake_production_handoffs_thread_id_fkey
    FOREIGN KEY (thread_id) REFERENCES public.intake_threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS intake_production_handoffs_client_idx
  ON public.intake_production_handoffs (client_slug, status);

-- ============================================================
-- Wire the production_handoff_id back-reference on intake_threads
-- ============================================================
ALTER TABLE public.intake_threads
  DROP CONSTRAINT IF EXISTS intake_threads_handoff_fkey;
ALTER TABLE public.intake_threads
  ADD CONSTRAINT intake_threads_handoff_fkey
  FOREIGN KEY (production_handoff_id)
  REFERENCES public.intake_production_handoffs(id)
  ON DELETE SET NULL;

-- ============================================================
-- Row-Level Security — tenant_slug isolation
--
-- Uses the existing set_app_tenant(slug) function from
-- 20260515_pilot_v1_phase1.sql. Caller MUST execute
-- `SELECT set_app_tenant('<client_slug>')` before any query.
-- ============================================================
ALTER TABLE public.intake_client_bots          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intake_threads              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intake_messages             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intake_board_rounds         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intake_production_handoffs  ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOR t IN
    SELECT unnest(ARRAY[
      'intake_client_bots',
      'intake_threads',
      'intake_messages',
      'intake_board_rounds',
      'intake_production_handoffs'
    ])
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I',
      t || '_tenant_isolation', t);
    EXECUTE format($f$
      CREATE POLICY %I ON public.%I
        FOR ALL
        USING (
          client_slug = current_setting('app.current_tenant_slug', true)
          OR current_setting('app.current_tenant_slug', true) = 'pi-ceo'
        )
        WITH CHECK (
          client_slug = current_setting('app.current_tenant_slug', true)
          OR current_setting('app.current_tenant_slug', true) = 'pi-ceo'
        )
    $f$, t || '_tenant_isolation', t);
  END LOOP;
END $$;

-- The 'pi-ceo' fallback lets the operator agent (running as 'pi-ceo'
-- tenant) read across all client_slug rows for administration. Each
-- per-client process MUST call `SELECT set_app_tenant('<slug>')` to
-- pin its tenant. See swarm/intake/SPEC.md §4 + the existing pattern
-- in supabase/migrations/20260515_pilot_v1_phase1.sql.

-- ============================================================
-- updated_at triggers — keep timestamps fresh
-- ============================================================
CREATE OR REPLACE FUNCTION public.intake_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOR t IN
    SELECT unnest(ARRAY[
      'intake_client_bots',
      'intake_threads',
      'intake_production_handoffs'
    ])
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
      t || '_set_updated_at', t);
    EXECUTE format($f$
      CREATE TRIGGER %I
      BEFORE UPDATE ON public.%I
      FOR EACH ROW
      EXECUTE FUNCTION public.intake_set_updated_at()
    $f$, t || '_set_updated_at', t);
  END LOOP;
END $$;
