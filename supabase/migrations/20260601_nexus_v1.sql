-- Nexus v1 — Autonomous Onboarding + Client Growth Operating System
-- Spec: 2nd-brain/Pitches/03-nexus-autonomous-onboarding-and-growth-os-v1.md §2
--
-- 8 tables: clients, client_workspaces, client_projects, client_channels,
--           client_loops, approvals, outcomes, nexus_audit
--
-- RLS pattern (per Pilot V1 ADR 004 §1 + CIP PR1 convention):
--   - clients: founder_id NOT NULL + per-founder isolation
--   - all other tables: workspace_slug NOT NULL + set_app_tenant() match
--   - nexus_audit: append-only (UPDATE/DELETE policies = false)
--
-- The set_app_tenant() function from Pilot V1 (`20260515_pilot_v1_phase1.sql`)
-- is already deployed; we reuse it.
--
-- Rollback (exact reverse order):
--   drop table if exists public.nexus_audit;
--   drop table if exists public.outcomes;
--   drop table if exists public.approvals;
--   drop table if exists public.client_loops;
--   drop table if exists public.client_channels;
--   drop table if exists public.client_projects;
--   drop table if exists public.client_workspaces;
--   drop table if exists public.clients;
--
-- This migration is APPLIED-DRY locally before prod application.
-- See `pyproject.toml` test gate; see PR body for the apply-to-prod runbook.

-- ============================================================
-- clients — pre-workspace intake records, founder-scoped
-- ============================================================

create table if not exists public.clients (
  id                    text         primary key,
  founder_id            text         not null,
  legal_name            text         not null,
  display_name          text         not null,
  industry              text,
  primary_contact_name  text,
  primary_contact_email text,
  status                text         not null default 'intake'
                                     check (status in (
                                       'intake', 'qualified', 'workspace_created',
                                       'wired', 'in_loop', 'paused', 'off_boarded'
                                     )),
  qualification         jsonb,
  intake_source         text         check (intake_source in (
                                       'voice', 'form', 'manual', 'referral'
                                     )),
  intake_recorded_at    timestamptz,
  created_at            timestamptz  not null default now(),
  updated_at            timestamptz  not null default now()
);

create index if not exists clients_founder_idx
  on public.clients (founder_id);
create index if not exists clients_status_created_idx
  on public.clients (status, created_at desc);

alter table public.clients enable row level security;
create policy founder_isolation_clients
  on public.clients
  using (founder_id = current_setting('app.current_founder_id', true));

-- ============================================================
-- client_workspaces — tenant scope per client
-- ============================================================

create table if not exists public.client_workspaces (
  id                text         primary key,
  client_id         text         not null references public.clients(id) on delete restrict,
  slug              text         not null unique,
  display_name      text         not null,
  github_org        text,
  github_repo       text,
  vercel_project    text,
  supabase_project  text,
  linear_team_id    text         not null,
  linear_project_id text,
  status            text         not null default 'active'
                                 check (status in ('active', 'paused', 'archived')),
  created_at        timestamptz  not null default now(),
  updated_at        timestamptz  not null default now()
);

create index if not exists client_workspaces_client_idx
  on public.client_workspaces (client_id);
create index if not exists client_workspaces_slug_idx
  on public.client_workspaces (slug);

alter table public.client_workspaces enable row level security;
create policy tenant_isolation_client_workspaces
  on public.client_workspaces
  using (slug = current_setting('app.current_tenant_slug', true));

-- ============================================================
-- client_projects — deliverables within a workspace
-- ============================================================

create table if not exists public.client_projects (
  id               text         primary key,
  workspace_id     text         not null references public.client_workspaces(id) on delete cascade,
  workspace_slug   text         not null,
  slug             text         not null,
  title            text         not null,
  description      text,
  status           text         not null default 'discovery'
                                check (status in ('discovery', 'active', 'done', 'cancelled')),
  owner_partner_id text,
  approval_policy  text         not null default 'creator_only'
                                check (approval_policy in (
                                  'creator_only', 'majority', 'custom'
                                )),
  linear_issue_id  text,
  github_pr_url    text,
  created_at       timestamptz  not null default now(),
  updated_at       timestamptz  not null default now(),
  unique (workspace_id, slug)
);

create index if not exists client_projects_workspace_idx
  on public.client_projects (workspace_slug);
create index if not exists client_projects_status_idx
  on public.client_projects (workspace_slug, status);

alter table public.client_projects enable row level security;
create policy tenant_isolation_client_projects
  on public.client_projects
  using (workspace_slug = current_setting('app.current_tenant_slug', true));

-- ============================================================
-- client_channels — Telegram / Slack / email mappings per workspace
-- ============================================================

create table if not exists public.client_channels (
  id                  text         primary key,
  workspace_id        text         not null references public.client_workspaces(id) on delete cascade,
  workspace_slug      text         not null,
  kind                text         not null
                                   check (kind in (
                                     'telegram_chat', 'telegram_bot', 'slack', 'email'
                                   )),
  external_id         text         not null,
  display_name        text         not null,
  bot_token_env_name  text,
  authorized_chat_ids text[],
  inbound_route       text         not null
                                   check (inbound_route in (
                                     'margot', 'support', 'ops-only'
                                   )),
  status              text         not null default 'active'
                                   check (status in ('active', 'paused', 'archived', 'pending')),
  provisioned_at      timestamptz,
  created_at          timestamptz  not null default now(),
  unique (kind, external_id)
);

create index if not exists client_channels_workspace_kind_idx
  on public.client_channels (workspace_slug, kind);

alter table public.client_channels enable row level security;
create policy tenant_isolation_client_channels
  on public.client_channels
  using (workspace_slug = current_setting('app.current_tenant_slug', true));

-- ============================================================
-- client_loops — autonomous loops enabled per workspace
-- ============================================================

create table if not exists public.client_loops (
  id              text         primary key,
  workspace_id    text         not null references public.client_workspaces(id) on delete cascade,
  workspace_slug  text         not null,
  loop_kind       text         not null
                               check (loop_kind in (
                                 'discovery', 'content', 'kpi', 'geo', 'support', 'compliance'
                               )),
  enabled         boolean      not null default true,
  cadence         text         not null,
  config          jsonb,
  last_run_at     timestamptz,
  next_run_at     timestamptz,
  created_at      timestamptz  not null default now(),
  unique (workspace_id, loop_kind)
);

create index if not exists client_loops_workspace_idx
  on public.client_loops (workspace_slug);
create index if not exists client_loops_next_run_idx
  on public.client_loops (enabled, next_run_at);

alter table public.client_loops enable row level security;
create policy tenant_isolation_client_loops
  on public.client_loops
  using (workspace_slug = current_setting('app.current_tenant_slug', true));

-- ============================================================
-- approvals — sensitive-action approval queue
-- ============================================================

create table if not exists public.approvals (
  id              text         primary key,
  workspace_id    text         references public.client_workspaces(id) on delete cascade,
  workspace_slug  text,
  requested_by    text         not null,
  action          text         not null,
  why_now         text         not null,
  reversibility   text         not null
                               check (reversibility in (
                                 'reversible', 'low', 'medium', 'high', 'irreversible'
                               )),
  risk_if_yes     text,
  risk_if_no      text,
  payload         jsonb        not null,
  status          text         not null default 'pending'
                               check (status in (
                                 'pending', 'approved', 'denied', 'auto-denied', 'expired'
                               )),
  decided_by      text,
  decided_at      timestamptz,
  decision_note   text,
  sla_expires_at  timestamptz  not null,
  created_at      timestamptz  not null default now()
);

create index if not exists approvals_status_sla_idx
  on public.approvals (status, sla_expires_at);
create index if not exists approvals_workspace_idx
  on public.approvals (workspace_slug);

alter table public.approvals enable row level security;
-- Portfolio-level rows (workspace_slug = null) require service-role access;
-- workspace-scoped rows match the current tenant.
create policy tenant_isolation_approvals
  on public.approvals
  using (
    workspace_slug = current_setting('app.current_tenant_slug', true)
    or workspace_slug is null
  );

-- ============================================================
-- outcomes — feedback loop signals attributed to workspace/project/persona
-- ============================================================

create table if not exists public.outcomes (
  id                  text                 primary key,
  workspace_id        text                 not null references public.client_workspaces(id) on delete cascade,
  workspace_slug      text                 not null,
  project_id          text                 references public.client_projects(id) on delete set null,
  persona_attribution text,
  source              text                 not null
                                           check (source in (
                                             'stripe', 'vercel', 'posthog',
                                             'sentry', 'linear', 'manual'
                                           )),
  metric              text                 not null,
  value_numeric       double precision,
  value_text          text,
  delta_window        text                 check (delta_window in ('24h', '7d', '30d')),
  captured_at         timestamptz          not null,
  raw_payload         jsonb,
  created_at          timestamptz          not null default now()
);

create index if not exists outcomes_workspace_captured_idx
  on public.outcomes (workspace_slug, captured_at desc);
create index if not exists outcomes_source_captured_idx
  on public.outcomes (source, captured_at desc);

alter table public.outcomes enable row level security;
create policy tenant_isolation_outcomes
  on public.outcomes
  using (workspace_slug = current_setting('app.current_tenant_slug', true));

-- ============================================================
-- nexus_audit — append-only audit ledger
-- ============================================================

create table if not exists public.nexus_audit (
  id              text         primary key,  -- 'nex-<hmac8>'
  ts_realtime     timestamptz  not null,
  ts_monotonic_ns bigint       not null,
  actor           text         not null,
  workspace_id    text,
  workspace_slug  text,
  client_id       text,
  action          text         not null,
  args_redacted   jsonb        not null,
  policy_level    text         not null
                               check (policy_level in ('auto', 'approval', 'escalation')),
  approval_id     text         references public.approvals(id) on delete set null,
  result          text         not null
                               check (result in ('ok', 'denied', 'error', 'timeout')),
  error_code      text,
  duration_ms     integer,
  outcomes_link   text         references public.outcomes(id) on delete set null
);

create index if not exists nexus_audit_workspace_ts_idx
  on public.nexus_audit (workspace_slug, ts_realtime desc);
create index if not exists nexus_audit_actor_ts_idx
  on public.nexus_audit (actor, ts_realtime desc);
create index if not exists nexus_audit_action_ts_idx
  on public.nexus_audit (action, ts_realtime desc);

alter table public.nexus_audit enable row level security;

-- Read policy: tenant-scoped (founder + workspace access)
create policy tenant_read_nexus_audit
  on public.nexus_audit
  for select
  using (
    workspace_slug = current_setting('app.current_tenant_slug', true)
    or workspace_slug is null
  );

-- Append-only: INSERT allowed for service role; UPDATE/DELETE never via RLS.
-- Service role bypasses RLS — that's how the application writes.
-- We do NOT create permissive update/delete policies; default-deny applies.

create policy nexus_audit_no_update
  on public.nexus_audit
  for update
  using (false);

create policy nexus_audit_no_delete
  on public.nexus_audit
  for delete
  using (false);

-- ============================================================
-- Verification (run after migration applies; this block is comments only)
-- ============================================================

-- Expected post-apply state:
--   select count(*) from information_schema.tables
--   where table_schema='public' and table_name in (
--     'clients','client_workspaces','client_projects','client_channels',
--     'client_loops','approvals','outcomes','nexus_audit'
--   );
--   -- expects 8
--
--   select tablename, rowsecurity from pg_tables
--   where schemaname='public' and tablename in (
--     'clients','client_workspaces','client_projects','client_channels',
--     'client_loops','approvals','outcomes','nexus_audit'
--   );
--   -- expects rowsecurity=true for all 8
--
--   select tablename, count(*) policy_count from pg_policies
--   where schemaname='public' and tablename in (
--     'clients','client_workspaces','client_projects','client_channels',
--     'client_loops','approvals','outcomes','nexus_audit'
--   )
--   group by tablename;
--   -- expects:
--   --   clients              | 1  (founder_isolation_clients)
--   --   client_workspaces    | 1  (tenant_isolation_client_workspaces)
--   --   client_projects      | 1  (tenant_isolation_client_projects)
--   --   client_channels      | 1  (tenant_isolation_client_channels)
--   --   client_loops         | 1  (tenant_isolation_client_loops)
--   --   approvals            | 1  (tenant_isolation_approvals)
--   --   outcomes             | 1  (tenant_isolation_outcomes)
--   --   nexus_audit          | 3  (tenant_read_nexus_audit, no_update, no_delete)
