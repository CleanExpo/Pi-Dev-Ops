-- 20260513000200_integration_schema.sql
-- Normalised cross-integration schema. Each integration has its own
-- write-path; the empire dashboard reads only from here.

BEGIN;

-- ── Sync state tracking (one row per integration) ──────────────────
CREATE TABLE IF NOT EXISTS public.integration_sync_state (
  integration TEXT PRIMARY KEY,                -- 'github' | 'vercel' | 'railway' | ...
  last_sync_started_at TIMESTAMPTZ,
  last_sync_completed_at TIMESTAMPTZ,
  last_sync_status TEXT,                       -- 'ok' | 'error' | 'partial'
  last_sync_error TEXT,
  rows_upserted INT DEFAULT 0,
  next_sync_due_at TIMESTAMPTZ
);

ALTER TABLE public.integration_sync_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS authenticated_read ON public.integration_sync_state;
DROP POLICY IF EXISTS service_role_write ON public.integration_sync_state;
CREATE POLICY authenticated_read ON public.integration_sync_state FOR SELECT TO authenticated USING (true);
CREATE POLICY service_role_write ON public.integration_sync_state FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ── GitHub ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_github_repos (
  id TEXT PRIMARY KEY,                         -- 'CleanExpo/RestoreAssist'
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  default_branch TEXT,
  is_private BOOLEAN,
  last_pushed_at TIMESTAMPTZ,
  open_prs_count INT,
  open_issues_count INT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_github_prs (
  id TEXT PRIMARY KEY,                         -- 'CleanExpo/RestoreAssist#946'
  repo TEXT NOT NULL REFERENCES public.integration_github_repos(id) ON DELETE CASCADE,
  number INT NOT NULL,
  title TEXT NOT NULL,
  state TEXT NOT NULL,                         -- 'open' | 'closed' | 'merged'
  author_login TEXT,
  author_email TEXT,
  head_ref TEXT,
  base_ref TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  merged_at TIMESTAMPTZ,
  mergeable TEXT,                              -- 'MERGEABLE' | 'CONFLICTING' | 'UNKNOWN'
  ci_state TEXT,                               -- 'success' | 'failure' | 'pending'
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_github_commits (
  sha TEXT PRIMARY KEY,
  repo TEXT NOT NULL REFERENCES public.integration_github_repos(id) ON DELETE CASCADE,
  author_login TEXT,
  author_email TEXT,
  committed_at TIMESTAMPTZ,
  message_subject TEXT,
  branch TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gh_commits_author_recent
  ON public.integration_github_commits(author_email, committed_at DESC);

CREATE TABLE IF NOT EXISTS public.integration_github_actions_runs (
  id BIGINT PRIMARY KEY,                       -- GitHub Actions run_id
  repo TEXT NOT NULL REFERENCES public.integration_github_repos(id) ON DELETE CASCADE,
  workflow_name TEXT,
  head_branch TEXT,
  head_sha TEXT,
  status TEXT,
  conclusion TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_github_secrets_index (
  -- NAMES ONLY — no values. Just a list of what's set per repo.
  repo TEXT NOT NULL REFERENCES public.integration_github_repos(id) ON DELETE CASCADE,
  secret_name TEXT NOT NULL,
  updated_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (repo, secret_name)
);

-- ── Vercel ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_vercel_projects (
  id TEXT PRIMARY KEY,                         -- prj_*
  name TEXT NOT NULL,
  framework TEXT,
  git_repo TEXT,                               -- 'CleanExpo/restoreassist'
  production_url TEXT,
  last_deployment_id TEXT,
  last_deployment_state TEXT,
  last_deployment_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_vercel_deployments (
  id TEXT PRIMARY KEY,                         -- dpl_*
  project_id TEXT NOT NULL REFERENCES public.integration_vercel_projects(id) ON DELETE CASCADE,
  url TEXT,
  state TEXT,                                  -- 'READY' | 'ERROR' | 'BUILDING'
  target TEXT,                                 -- 'production' | 'preview'
  commit_sha TEXT,
  commit_message TEXT,
  ready_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_vercel_env_index (
  project_id TEXT NOT NULL REFERENCES public.integration_vercel_projects(id) ON DELETE CASCADE,
  env_target TEXT NOT NULL,                    -- 'production' | 'preview' | 'development'
  key TEXT NOT NULL,
  is_empty BOOLEAN NOT NULL,                   -- TRUE if the value is "" (the smoking-gun pattern from this session)
  value_length INT,
  updated_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, env_target, key)
);

-- ── Railway ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_railway_services (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  last_deployment_id TEXT,
  last_deployment_status TEXT,
  last_deployment_at TIMESTAMPTZ,
  service_url TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_railway_deployments (
  id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES public.integration_railway_services(id) ON DELETE CASCADE,
  status TEXT,                                 -- 'SUCCESS' | 'FAILED' | 'BUILDING' | 'DEPLOYING'
  commit_sha TEXT,
  created_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── DigitalOcean ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_do_apps (
  id TEXT PRIMARY KEY,                         -- DO App ID
  name TEXT NOT NULL,
  project_name TEXT,                           -- DO Project (Carsi, Synthex, etc.)
  region TEXT,
  live_url TEXT,
  active_deployment_id TEXT,
  active_deployment_phase TEXT,
  last_deployment_phase TEXT,
  last_deployment_progress_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_do_droplets (
  id BIGINT PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT,
  size TEXT,
  status TEXT,
  ipv4 TEXT,
  created_at TIMESTAMPTZ,
  monthly_cost_usd NUMERIC(10,2),
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_do_databases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  engine TEXT,
  version TEXT,
  status TEXT,
  region TEXT,
  monthly_cost_usd NUMERIC(10,2),
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Supabase Advisor findings (per-project) ────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_supabase_projects (
  ref TEXT PRIMARY KEY,                        -- the project ref like 'lksfwktwtmyznckodsau'
  name TEXT NOT NULL,
  region TEXT,
  status TEXT,                                 -- 'ACTIVE_HEALTHY' | etc.
  pg_version TEXT,
  total_advisor_findings INT,
  advisor_errors INT,
  advisor_warns INT,
  advisor_infos INT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_supabase_advisor_findings (
  id BIGSERIAL PRIMARY KEY,
  project_ref TEXT NOT NULL REFERENCES public.integration_supabase_projects(ref) ON DELETE CASCADE,
  finding_name TEXT NOT NULL,                  -- 'rls_disabled_in_public' | etc.
  severity TEXT NOT NULL,                      -- 'ERROR' | 'WARN' | 'INFO'
  detail TEXT,
  resource_name TEXT,                          -- the table / function / view name
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_advisor_findings_project_severity
  ON public.integration_supabase_advisor_findings(project_ref, severity);

-- ── 1Password (NAMES ONLY) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_onepassword_index (
  vault TEXT NOT NULL,
  item_name TEXT NOT NULL,
  category TEXT,                               -- 'API Credential' | 'Password' | 'Document' etc.
  last_modified TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (vault, item_name)
);

-- ── Linear (extends existing Linear MCP usage) ─────────────────────
CREATE TABLE IF NOT EXISTS public.integration_linear_teams (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key TEXT NOT NULL,
  active_cycle_id TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_linear_projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  team_id TEXT REFERENCES public.integration_linear_teams(id),
  state TEXT,                                  -- 'planned' | 'started' | 'paused' | 'completed' | 'canceled'
  progress NUMERIC,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_linear_issues (
  id TEXT PRIMARY KEY,                         -- 'RA-3008'
  team_id TEXT REFERENCES public.integration_linear_teams(id),
  project_id TEXT REFERENCES public.integration_linear_projects(id),
  title TEXT NOT NULL,
  state_name TEXT,
  state_type TEXT,
  priority INT,
  assignee_id TEXT,
  assignee_name TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_linear_issues_assignee_state
  ON public.integration_linear_issues(assignee_id, state_type);

-- ── Stripe ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_stripe_subscriptions (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  status TEXT,
  current_period_end TIMESTAMPTZ,
  monthly_amount_aud NUMERIC(10,2),
  product_name TEXT,
  created_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.integration_stripe_invoices_mtd (
  -- Month-to-date roll-up — refreshed on each sync
  yyyymm TEXT PRIMARY KEY,                     -- '202605'
  total_aud NUMERIC(12,2),
  paid_aud NUMERIC(12,2),
  outstanding_aud NUMERIC(12,2),
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Composio ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.integration_composio_connections (
  id TEXT PRIMARY KEY,                         -- Composio connection ID
  toolkit_slug TEXT NOT NULL,                  -- 'gmail' | 'google-calendar' | etc.
  user_email TEXT,
  status TEXT,                                 -- 'ACTIVE' | 'EXPIRED' | etc.
  last_used_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── RLS on every integration_* table — service-role write, authenticated read ─
DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name LIKE 'integration_%'
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS authenticated_read ON public.%I', t);
        EXECUTE format('DROP POLICY IF EXISTS service_role_write ON public.%I', t);
        EXECUTE format('CREATE POLICY authenticated_read ON public.%I FOR SELECT TO authenticated USING (true)', t);
        EXECUTE format(
            'CREATE POLICY service_role_write ON public.%I FOR ALL TO service_role '
            'USING (true) WITH CHECK (true)',
            t
        );
    END LOOP;
END $$;

COMMIT;
