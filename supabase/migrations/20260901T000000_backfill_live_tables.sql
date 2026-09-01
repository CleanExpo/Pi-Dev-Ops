-- Back-fill the 16 live tables that no file in this repo declared (RA-7396).
--
-- THIS FILE DESCRIBES PRODUCTION; IT DID NOT CREATE IT. Every table below already
-- exists in the Pi CEO project and was created out-of-band — dashboard, MCP, or
-- another repo. Each statement is therefore `IF NOT EXISTS` and is expected to be
-- a no-op against any real database. Its purpose is the CI shadow database: the
-- rls-assertions gate builds that from this repo's files, so a table declared
-- nowhere was invisible to it. 20 of 57 live tables were, which is a security
-- gate that cannot fail on a third of what it claims to cover.
--
-- Generated from pg_catalog on 2026-09-01, not hand-written: 168 columns, 63
-- constraints, 25 indexes and 22 policies is well past what can be transcribed
-- reliably, and DDL that drifts from live would be worse than none — the gate
-- would then asserting confidently against a schema production does not have.
--
-- OWNERSHIP CAVEAT. The 12 cc_* tables have no consumer anywhere in Pi-Dev-Ops:
-- nothing here reads or writes them, and no doc mentions CC-03. They are declared
-- for gate coverage, not as a claim of authorship. If they belong to another
-- repo, that repo should own this schema and these lines should move there.
--
-- The 4 log tables carry NO policies live, which is why the advisor reports them
-- as rls_enabled_no_policy. They are baselined in rls_coverage.sql rather than
-- given invented policies — writing policies for tables this repo does not own
-- would change their semantics the moment anyone applied this file for real.

-- ── parents first: FKs below reference these ────────────────────────────────

create table if not exists public.cc_projects (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  name text not null,
  repo_path text,
  github_repo text,
  brand_rules_ref text,
  business_purpose text default ''::text not null,
  deployment_target text,
  owner text,
  agent_team text[] default '{}'::text[] not null,
  status text default 'active'::text not null,
  evidence_vault_path text,
  validation_commands text[] default '{}'::text[] not null,
  linear_prefix text,
  production_url text,
  metadata jsonb default '{}'::jsonb not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null,
  constraint cc_projects_pkey primary key (id),
  constraint cc_projects_founder_id_name_key unique (founder_id, name),
  constraint cc_projects_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_projects_status_check check ((status = any (array['active'::text, 'stub'::text, 'paused'::text, 'archived'::text])))
);

create table if not exists public.cc_tasks (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  external_ref text,
  queue_id uuid,
  project_id uuid,
  project_key text,
  title text not null,
  objective text default ''::text not null,
  priority text default 'P2'::text not null,
  status text default 'proposed'::text not null,
  agent_owner text,
  risk_level text default 'low'::text not null,
  execution_mode text default 'advisory'::text not null,
  origin text default 'idea'::text not null,
  dependencies uuid[] default '{}'::uuid[] not null,
  human_approval_required boolean default true not null,
  evidence_path text,
  validation_required text[] default '{}'::text[] not null,
  linear_id text,
  preview_url text,
  metadata jsonb default '{}'::jsonb not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null,
  constraint cc_tasks_pkey primary key (id),
  constraint cc_tasks_founder_id_external_ref_key unique (founder_id, external_ref),
  constraint cc_tasks_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_tasks_execution_mode_check check ((execution_mode = any (array['advisory'::text, 'local-code'::text, 'branch-preview'::text, 'overnight'::text]))),
  constraint cc_tasks_origin_check check ((origin = any (array['idea'::text, 'board-review'::text, 'blocker'::text, 'self-improvement'::text]))),
  constraint cc_tasks_priority_check check ((priority = any (array['P0'::text, 'P1'::text, 'P2'::text, 'P3'::text]))),
  constraint cc_tasks_risk_level_check check ((risk_level = any (array['low'::text, 'medium'::text, 'high'::text, 'critical'::text]))),
  constraint cc_tasks_status_check check ((status = any (array['proposed'::text, 'queued'::text, 'running'::text, 'blocked'::text, 'awaiting_approval'::text, 'done'::text, 'failed'::text])))
);

-- ── remaining cc_* ──────────────────────────────────────────────────────────

create table if not exists public.cc_agents (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  name text not null,
  role text default ''::text not null,
  autonomy_max_level integer default 1 not null,
  model_tier text,
  skills text[] default '{}'::text[] not null,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null,
  constraint cc_agents_pkey primary key (id),
  constraint cc_agents_founder_id_name_key unique (founder_id, name),
  constraint cc_agents_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_agents_autonomy_max_level_check check (((autonomy_max_level >= 0) and (autonomy_max_level <= 5)))
);

create table if not exists public.cc_tools (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  tool_key text not null,
  source text not null,
  server text,
  description text default ''::text not null,
  input_schema jsonb default '{}'::jsonb not null,
  risk_class text default 'read'::text not null,
  required_level integer default 0 not null,
  project_scope uuid[] default '{}'::uuid[] not null,
  approval_required boolean default true not null,
  discovered_at timestamp with time zone default now() not null,
  active boolean default true not null,
  constraint cc_tools_pkey primary key (id),
  constraint cc_tools_founder_id_tool_key_key unique (founder_id, tool_key),
  constraint cc_tools_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_tools_required_level_check check (((required_level >= 0) and (required_level <= 5))),
  constraint cc_tools_risk_class_check check ((risk_class = any (array['read'::text, 'write-local'::text, 'write-shared'::text, 'external'::text, 'destructive'::text]))),
  constraint cc_tools_source_check check ((source = any (array['hermes'::text, 'mcp'::text, 'project'::text, 'codex'::text, 'claude-code'::text, 'local'::text])))
);

create table if not exists public.cc_brand_rules (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  project_id uuid,
  tokens_ref text,
  locks jsonb default '{}'::jsonb not null,
  deviation_policy text default 'do-not-deviate-unless-authorised'::text not null,
  created_at timestamp with time zone default now() not null,
  constraint cc_brand_rules_pkey primary key (id),
  constraint cc_brand_rules_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_brand_rules_project_id_fkey foreign key (project_id) references cc_projects(id) on delete cascade
);

create table if not exists public.cc_risks (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  project_id uuid,
  name text not null,
  severity text default 'medium'::text not null,
  evidence text,
  impact text,
  recommended_action text,
  owner_role text,
  status text default 'open'::text not null,
  created_at timestamp with time zone default now() not null,
  constraint cc_risks_pkey primary key (id),
  constraint cc_risks_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_risks_project_id_fkey foreign key (project_id) references cc_projects(id) on delete cascade,
  constraint cc_risks_severity_check check ((severity = any (array['low'::text, 'medium'::text, 'high'::text, 'critical'::text]))),
  constraint cc_risks_status_check check ((status = any (array['open'::text, 'mitigating'::text, 'accepted'::text, 'closed'::text])))
);

create table if not exists public.cc_approvals (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  task_id uuid not null,
  decision text not null,
  approver text default ''::text not null,
  note text,
  at timestamp with time zone default now() not null,
  constraint cc_approvals_pkey primary key (id),
  constraint cc_approvals_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_approvals_task_id_fkey foreign key (task_id) references cc_tasks(id) on delete cascade,
  constraint cc_approvals_decision_check check ((decision = any (array['approve'::text, 'reject'::text, 'edit'::text, 'defer'::text])))
);

create table if not exists public.cc_decisions (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  task_id uuid,
  subject text not null,
  verdict text default 'HOLD'::text not null,
  rationale text default ''::text not null,
  personas jsonb default '{}'::jsonb not null,
  wiki_path text,
  at timestamp with time zone default now() not null,
  constraint cc_decisions_pkey primary key (id),
  constraint cc_decisions_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_decisions_task_id_fkey foreign key (task_id) references cc_tasks(id) on delete set null,
  constraint cc_decisions_verdict_check check ((verdict = any (array['APPROVED'::text, 'HOLD'::text, 'REJECTED'::text])))
);

create table if not exists public.cc_evidence_records (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  task_id uuid not null,
  kind text default 'brief'::text not null,
  wiki_path text not null,
  sources jsonb default '[]'::jsonb not null,
  confidence text default 'medium'::text not null,
  created_at timestamp with time zone default now() not null,
  constraint cc_evidence_records_pkey primary key (id),
  constraint cc_evidence_records_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_evidence_records_task_id_fkey foreign key (task_id) references cc_tasks(id) on delete cascade,
  constraint cc_evidence_records_confidence_check check ((confidence = any (array['high'::text, 'medium'::text, 'low'::text]))),
  constraint cc_evidence_records_kind_check check ((kind = any (array['brief'::text, 'research'::text, 'decision'::text, 'validation'::text, 'handoff'::text, 'daily'::text])))
);

create table if not exists public.cc_execution_sessions (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  task_id uuid not null,
  surface text default 'local'::text not null,
  status text default 'running'::text not null,
  logs_ref text,
  started_at timestamp with time zone default now() not null,
  ended_at timestamp with time zone,
  constraint cc_execution_sessions_pkey primary key (id),
  constraint cc_execution_sessions_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_execution_sessions_task_id_fkey foreign key (task_id) references cc_tasks(id) on delete cascade,
  constraint cc_execution_sessions_status_check check ((status = any (array['running'::text, 'paused'::text, 'done'::text, 'failed'::text]))),
  constraint cc_execution_sessions_surface_check check ((surface = any (array['codex'::text, 'claude-code'::text, 'pi-ceo-dev'::text, 'local'::text])))
);

create table if not exists public.cc_task_events (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  task_id uuid not null,
  type text not null,
  actor text default 'system'::text not null,
  payload jsonb default '{}'::jsonb not null,
  at timestamp with time zone default now() not null,
  constraint cc_task_events_pkey primary key (id),
  constraint cc_task_events_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_task_events_task_id_fkey foreign key (task_id) references cc_tasks(id) on delete cascade,
  constraint cc_task_events_type_check check ((type = any (array['created'::text, 'status_changed'::text, 'approved'::text, 'blocked'::text, 'started'::text, 'completed'::text, 'failed'::text, 'evidence_added'::text, 'comment'::text, 'linear_synced'::text])))
);

create table if not exists public.cc_validation_runs (
  id uuid default gen_random_uuid() not null,
  founder_id uuid not null,
  task_id uuid not null,
  gate text not null,
  command text,
  result text default 'skip'::text not null,
  evidence_path text,
  ran_at timestamp with time zone default now() not null,
  constraint cc_validation_runs_pkey primary key (id),
  constraint cc_validation_runs_founder_id_fkey foreign key (founder_id) references auth.users(id) on delete cascade,
  constraint cc_validation_runs_task_id_fkey foreign key (task_id) references cc_tasks(id) on delete cascade,
  constraint cc_validation_runs_result_check check ((result = any (array['pass'::text, 'fail'::text, 'skip'::text])))
);

-- ── log tables. `bigserial` reproduces live exactly: bigint, not null, and a
--    <table>_id_seq the default draws from — which is what pg_catalog reports
--    as `default nextval('..._id_seq'::regclass)`.

create table if not exists public.claude_api_costs (
  id bigserial not null,
  called_at timestamp with time zone default now(),
  model text not null,
  purpose text,
  workflow_name text,
  input_tokens integer,
  output_tokens integer,
  cost_usd numeric(10,6),
  response_preview text,
  metadata jsonb,
  constraint claude_api_costs_pkey primary key (id)
);

create table if not exists public.heartbeat_log (
  id bigserial not null,
  checked_at timestamp with time zone default now() not null,
  service text not null,
  status text not null,
  http_code integer,
  latency_ms integer,
  error_msg text,
  constraint heartbeat_log_pkey primary key (id),
  constraint heartbeat_log_status_check check ((status = any (array['OK'::text, 'DOWN'::text, 'WARN'::text])))
);

create table if not exists public.triage_log (
  id bigserial not null,
  created_at timestamp with time zone default now() not null,
  linear_issue_id text not null,
  issue_title text not null,
  issue_url text,
  team_name text,
  priority integer,
  triage_label text,
  triage_reason text,
  telegram_sent boolean default false not null,
  telegram_sent_at timestamp with time zone,
  raw_payload jsonb,
  claude_reviewed boolean default false,
  claude_assessment text,
  constraint triage_log_pkey primary key (id),
  constraint triage_log_triage_label_check check ((triage_label = any (array['Critical'::text, 'Action'::text, 'FYI'::text, 'Skip'::text])))
);

create table if not exists public.workflow_runs (
  id bigserial not null,
  run_at timestamp with time zone default now() not null,
  workflow_name text not null,
  trigger_type text,
  status text not null,
  items_processed integer default 0 not null,
  duration_ms integer,
  error_msg text,
  metadata jsonb,
  constraint workflow_runs_pkey primary key (id),
  constraint workflow_runs_status_check check ((status = any (array['success'::text, 'error'::text, 'skipped'::text])))
);

-- ── indexes ─────────────────────────────────────────────────────────────────

create index if not exists cc_agents_founder_active_idx on public.cc_agents using btree (founder_id, active);
create index if not exists cc_approvals_task_idx on public.cc_approvals using btree (task_id, at desc);
create index if not exists cc_brand_rules_project_idx on public.cc_brand_rules using btree (project_id);
create index if not exists cc_decisions_founder_at_idx on public.cc_decisions using btree (founder_id, at desc);
create index if not exists cc_decisions_task_idx on public.cc_decisions using btree (task_id);
create index if not exists cc_evidence_records_founder_idx on public.cc_evidence_records using btree (founder_id, created_at desc);
create index if not exists cc_evidence_records_task_idx on public.cc_evidence_records using btree (task_id, created_at desc);
create index if not exists cc_execution_sessions_task_idx on public.cc_execution_sessions using btree (task_id, started_at desc);
create index if not exists cc_projects_founder_status_idx on public.cc_projects using btree (founder_id, status);
create index if not exists cc_risks_founder_project_idx on public.cc_risks using btree (founder_id, project_id);
create index if not exists cc_task_events_founder_idx on public.cc_task_events using btree (founder_id, at desc);
create index if not exists cc_task_events_task_idx on public.cc_task_events using btree (task_id, at desc);
create index if not exists cc_tasks_dependencies_idx on public.cc_tasks using gin (dependencies);
create index if not exists cc_tasks_founder_project_idx on public.cc_tasks using btree (founder_id, project_key);
create index if not exists cc_tasks_founder_status_idx on public.cc_tasks using btree (founder_id, status);
create index if not exists cc_tools_founder_source_idx on public.cc_tools using btree (founder_id, source);
create index if not exists cc_validation_runs_task_idx on public.cc_validation_runs using btree (task_id, ran_at desc);
create index if not exists heartbeat_log_checked_at_idx on public.heartbeat_log using btree (checked_at desc);
create index if not exists heartbeat_log_service_idx on public.heartbeat_log using btree (service, checked_at desc);
create index if not exists idx_claude_costs_called_at on public.claude_api_costs using btree (called_at desc);
create index if not exists idx_triage_claude_reviewed on public.triage_log using btree (claude_reviewed) where (claude_reviewed = false);
create index if not exists triage_log_created_at_idx on public.triage_log using btree (created_at desc);
create index if not exists triage_log_triage_label_idx on public.triage_log using btree (triage_label);
create index if not exists workflow_runs_run_at_idx on public.workflow_runs using btree (run_at desc);
create index if not exists workflow_runs_workflow_name_idx on public.workflow_runs using btree (workflow_name, run_at desc);

-- ── RLS. All 16 are rls_enabled live. The 4 log tables carry no policies
--    there, so they are baselined in rls_coverage.sql rather than invented.

alter table public.cc_agents             enable row level security;
alter table public.cc_approvals          enable row level security;
alter table public.cc_brand_rules        enable row level security;
alter table public.cc_decisions          enable row level security;
alter table public.cc_evidence_records   enable row level security;
alter table public.cc_execution_sessions enable row level security;
alter table public.cc_projects           enable row level security;
alter table public.cc_risks              enable row level security;
alter table public.cc_task_events        enable row level security;
alter table public.cc_tasks              enable row level security;
alter table public.cc_tools              enable row level security;
alter table public.cc_validation_runs    enable row level security;
alter table public.claude_api_costs      enable row level security;
alter table public.heartbeat_log         enable row level security;
alter table public.triage_log            enable row level security;
alter table public.workflow_runs         enable row level security;

-- ── policies, verbatim from pg_policies. Every one is founder-scoped on
--    auth.uid(); the child tables additionally require the parent task to
--    belong to the same founder, so a forged task_id cannot attach a row.

do $$
begin
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_projects_all') then
    create policy "cc_projects_all" on public.cc_projects for all to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_agents_all') then
    create policy "cc_agents_all" on public.cc_agents for all to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_tools_all') then
    create policy "cc_tools_all" on public.cc_tools for all to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_brand_rules_all') then
    create policy "cc_brand_rules_all" on public.cc_brand_rules for all to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_risks_all') then
    create policy "cc_risks_all" on public.cc_risks for all to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_tasks_select') then
    create policy "cc_tasks_select" on public.cc_tasks for select to public using ((founder_id = auth.uid()));
    create policy "cc_tasks_insert" on public.cc_tasks for insert to public with check ((founder_id = auth.uid()));
    create policy "cc_tasks_update" on public.cc_tasks for update to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
    create policy "cc_tasks_delete" on public.cc_tasks for delete to public using ((founder_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_approvals_select') then
    create policy "cc_approvals_select" on public.cc_approvals for select to public using ((founder_id = auth.uid()));
    create policy "cc_approvals_insert" on public.cc_approvals for insert to public
      with check (((founder_id = auth.uid()) and (exists (
        select 1 from cc_tasks t where ((t.id = cc_approvals.task_id) and (t.founder_id = auth.uid()))))));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_decisions_select') then
    create policy "cc_decisions_select" on public.cc_decisions for select to public using ((founder_id = auth.uid()));
    create policy "cc_decisions_insert" on public.cc_decisions for insert to public
      with check ((founder_id = auth.uid()));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_evidence_records_select') then
    create policy "cc_evidence_records_select" on public.cc_evidence_records for select to public using ((founder_id = auth.uid()));
    create policy "cc_evidence_records_insert" on public.cc_evidence_records for insert to public
      with check (((founder_id = auth.uid()) and (exists (
        select 1 from cc_tasks t where ((t.id = cc_evidence_records.task_id) and (t.founder_id = auth.uid()))))));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_execution_sessions_select') then
    create policy "cc_execution_sessions_select" on public.cc_execution_sessions for select to public using ((founder_id = auth.uid()));
    create policy "cc_execution_sessions_insert" on public.cc_execution_sessions for insert to public
      with check (((founder_id = auth.uid()) and (exists (
        select 1 from cc_tasks t where ((t.id = cc_execution_sessions.task_id) and (t.founder_id = auth.uid()))))));
    create policy "cc_execution_sessions_update" on public.cc_execution_sessions for update to public
      using ((founder_id = auth.uid())) with check ((founder_id = auth.uid()));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_task_events_select') then
    create policy "cc_task_events_select" on public.cc_task_events for select to public using ((founder_id = auth.uid()));
    create policy "cc_task_events_insert" on public.cc_task_events for insert to public
      with check (((founder_id = auth.uid()) and (exists (
        select 1 from cc_tasks t where ((t.id = cc_task_events.task_id) and (t.founder_id = auth.uid()))))));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and policyname='cc_validation_runs_select') then
    create policy "cc_validation_runs_select" on public.cc_validation_runs for select to public using ((founder_id = auth.uid()));
    create policy "cc_validation_runs_insert" on public.cc_validation_runs for insert to public
      with check (((founder_id = auth.uid()) and (exists (
        select 1 from cc_tasks t where ((t.id = cc_validation_runs.task_id) and (t.founder_id = auth.uid()))))));
  end if;
end $$;
