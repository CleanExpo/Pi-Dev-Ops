-- Migration: Client Intake Pipeline — partner-shared workspace rework (CIP-PR1B).
--
-- 2026-05-26 update: Phill confirmed Duncan + Toby are business
-- partners, not clients. All 3 share visibility of every project.
-- Per-partner Telegram bots remain (for attribution) but the data
-- model now treats "project" as the first-class entity, not "client
-- tenant".
--
-- This migration:
--   1. Adds `intake_partners` (3 rows: phill, duncan, toby)
--   2. Adds `intake_projects` (first-class shared project entity)
--   3. ALTER existing tables to add partner attribution + project FK
--   4. Reworks RLS policies: any row where client_slug='unite-group'
--      OR current tenant='pi-ceo' is readable/writable by all 3
--      partners. Per-partner restrictions are an application-layer
--      concern (use partner_id columns), not RLS.
--
-- Apply via Supabase MCP `apply_migration` per
-- unite-group-ci-recovery skill §3.1.

-- ============================================================
-- intake_partners — 3 partners in the Unite-Group workspace
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_partners (
  id              TEXT        PRIMARY KEY,
  partner_slug    TEXT        NOT NULL UNIQUE,
  display_name    TEXT        NOT NULL,
  email           TEXT,
  telegram_user_id BIGINT,    -- so we can tag inbound messages back to the right partner
  workspace_slug  TEXT        NOT NULL DEFAULT 'unite-group',
  status          TEXT        NOT NULL DEFAULT 'active',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT intake_partners_status_check
    CHECK (status IN ('active', 'paused', 'archived'))
);
CREATE INDEX IF NOT EXISTS intake_partners_workspace_idx
  ON public.intake_partners (workspace_slug);

-- ============================================================
-- intake_projects — first-class shared project entity
-- ============================================================
CREATE TABLE IF NOT EXISTS public.intake_projects (
  id                 TEXT        PRIMARY KEY,
  workspace_slug     TEXT        NOT NULL DEFAULT 'unite-group',
  name               TEXT        NOT NULL,
  slug               TEXT        NOT NULL,
  description        TEXT,
  owner_partner_id   TEXT        NOT NULL,
  status             TEXT        NOT NULL DEFAULT 'discovery',
  approval_policy    TEXT        NOT NULL DEFAULT 'creator_only',
  github_repo        TEXT,       -- e.g. 'CleanExpo/Acme-Marketing-Platform'; set on production handoff
  linear_team_id     TEXT,
  linear_project_id  TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  shipped_at         TIMESTAMPTZ,
  CONSTRAINT intake_projects_status_check
    CHECK (status IN ('discovery', 'in_board', 'awaiting_creator', 'ready_for_production', 'shipped', 'cancelled', 'paused_human_review')),
  CONSTRAINT intake_projects_approval_check
    CHECK (approval_policy IN ('creator_only', 'all_partners', 'majority', 'custom')),
  CONSTRAINT intake_projects_owner_fkey
    FOREIGN KEY (owner_partner_id) REFERENCES public.intake_partners(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS intake_projects_workspace_slug_uniq
  ON public.intake_projects (workspace_slug, slug);
CREATE INDEX IF NOT EXISTS intake_projects_owner_idx
  ON public.intake_projects (owner_partner_id);
CREATE INDEX IF NOT EXISTS intake_projects_status_idx
  ON public.intake_projects (workspace_slug, status);

-- ============================================================
-- ALTER intake_client_bots — link each bot to a partner
-- ============================================================
ALTER TABLE public.intake_client_bots
  ADD COLUMN IF NOT EXISTS partner_id TEXT,
  ADD COLUMN IF NOT EXISTS workspace_slug TEXT NOT NULL DEFAULT 'unite-group';

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema='public' AND table_name='intake_client_bots'
      AND constraint_name='intake_client_bots_partner_fkey'
  ) THEN
    ALTER TABLE public.intake_client_bots
      ADD CONSTRAINT intake_client_bots_partner_fkey
      FOREIGN KEY (partner_id) REFERENCES public.intake_partners(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS intake_client_bots_partner_idx
  ON public.intake_client_bots (partner_id);

-- ============================================================
-- ALTER intake_threads — link to project + drop strict isolation
-- ============================================================
ALTER TABLE public.intake_threads
  ADD COLUMN IF NOT EXISTS project_id TEXT,
  ADD COLUMN IF NOT EXISTS workspace_slug TEXT NOT NULL DEFAULT 'unite-group',
  ADD COLUMN IF NOT EXISTS margot_state TEXT NOT NULL DEFAULT 'awaiting_project_name';

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema='public' AND table_name='intake_threads'
      AND constraint_name='intake_threads_project_fkey'
  ) THEN
    ALTER TABLE public.intake_threads
      ADD CONSTRAINT intake_threads_project_fkey
      FOREIGN KEY (project_id) REFERENCES public.intake_projects(id) ON DELETE SET NULL;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema='public' AND table_name='intake_threads'
      AND constraint_name='intake_threads_margot_state_check'
  ) THEN
    ALTER TABLE public.intake_threads
      ADD CONSTRAINT intake_threads_margot_state_check
      CHECK (margot_state IN ('awaiting_project_name', 'awaiting_idea', 'classified', 'in_loop'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS intake_threads_project_idx
  ON public.intake_threads (project_id);

-- ============================================================
-- ALTER intake_messages — partner attribution
-- ============================================================
ALTER TABLE public.intake_messages
  ADD COLUMN IF NOT EXISTS submitted_by_partner_id TEXT,
  ADD COLUMN IF NOT EXISTS workspace_slug TEXT NOT NULL DEFAULT 'unite-group';

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema='public' AND table_name='intake_messages'
      AND constraint_name='intake_messages_partner_fkey'
  ) THEN
    ALTER TABLE public.intake_messages
      ADD CONSTRAINT intake_messages_partner_fkey
      FOREIGN KEY (submitted_by_partner_id) REFERENCES public.intake_partners(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS intake_messages_partner_idx
  ON public.intake_messages (submitted_by_partner_id);

-- ============================================================
-- ALTER intake_board_rounds + intake_production_handoffs
-- ============================================================
ALTER TABLE public.intake_board_rounds
  ADD COLUMN IF NOT EXISTS workspace_slug TEXT NOT NULL DEFAULT 'unite-group';

ALTER TABLE public.intake_production_handoffs
  ADD COLUMN IF NOT EXISTS workspace_slug TEXT NOT NULL DEFAULT 'unite-group',
  ADD COLUMN IF NOT EXISTS triggered_by_partner_id TEXT;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema='public' AND table_name='intake_production_handoffs'
      AND constraint_name='intake_production_handoffs_partner_fkey'
  ) THEN
    ALTER TABLE public.intake_production_handoffs
      ADD CONSTRAINT intake_production_handoffs_partner_fkey
      FOREIGN KEY (triggered_by_partner_id) REFERENCES public.intake_partners(id) ON DELETE SET NULL;
  END IF;
END $$;

-- ============================================================
-- RLS REWORK — partner-shared workspace
--
-- All 3 partners see every row in the workspace. Strict per-partner
-- isolation is gone (it was wrong-shaped for partners-not-clients).
-- Attribution lives in the partner_id columns, NOT in RLS.
-- ============================================================

-- Enable RLS on the two new tables
ALTER TABLE public.intake_partners ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intake_projects ENABLE ROW LEVEL SECURITY;

-- Drop the old per-client-slug policies on the 5 PR1 tables + 2 new
-- tables and replace with workspace-scoped policies.
DO $$
DECLARE
  t TEXT;
  policy_name TEXT;
BEGIN
  FOR t IN
    SELECT unnest(ARRAY[
      'intake_partners',
      'intake_projects',
      'intake_client_bots',
      'intake_threads',
      'intake_messages',
      'intake_board_rounds',
      'intake_production_handoffs'
    ])
  LOOP
    -- Drop old isolation policy if it exists (from PR1)
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I',
      t || '_tenant_isolation', t);
    -- Drop any prior workspace policy if re-running
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I',
      t || '_workspace_access', t);

    -- Create new workspace-scoped policy:
    -- Pass if the current tenant matches the workspace_slug (default 'unite-group'),
    -- OR is the 'pi-ceo' admin tenant.
    EXECUTE format($f$
      CREATE POLICY %I ON public.%I
        FOR ALL
        USING (
          workspace_slug = current_setting('app.current_tenant_slug', true)
          OR current_setting('app.current_tenant_slug', true) = 'pi-ceo'
        )
        WITH CHECK (
          workspace_slug = current_setting('app.current_tenant_slug', true)
          OR current_setting('app.current_tenant_slug', true) = 'pi-ceo'
        )
    $f$, t || '_workspace_access', t);
  END LOOP;
END $$;

-- ============================================================
-- updated_at triggers for the 2 new tables
-- ============================================================
DROP TRIGGER IF EXISTS intake_partners_set_updated_at ON public.intake_partners;
CREATE TRIGGER intake_partners_set_updated_at
  BEFORE UPDATE ON public.intake_partners
  FOR EACH ROW
  EXECUTE FUNCTION public.intake_set_updated_at();

DROP TRIGGER IF EXISTS intake_projects_set_updated_at ON public.intake_projects;
CREATE TRIGGER intake_projects_set_updated_at
  BEFORE UPDATE ON public.intake_projects
  FOR EACH ROW
  EXECUTE FUNCTION public.intake_set_updated_at();

-- ============================================================
-- Seed the 3 partners
-- (idempotent — ON CONFLICT DO NOTHING)
-- ============================================================
INSERT INTO public.intake_partners (id, partner_slug, display_name, workspace_slug)
VALUES
  ('partner_phill', 'phill', 'Phill McGurk', 'unite-group'),
  ('partner_duncan', 'duncan', 'Duncan', 'unite-group'),
  ('partner_toby', 'toby', 'Toby', 'unite-group')
ON CONFLICT (partner_slug) DO NOTHING;
