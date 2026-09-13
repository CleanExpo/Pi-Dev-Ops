-- RA-7536 — declare 12 tables that exist in the live Pi CEO database but that no
-- migration declared: the placecards family, goal_card_runs, the coaching family
-- and lead_verifications. They were created outside this repo, so the
-- rls-assertions shadow database never contained them and scripts/schema_drift_check.py
-- flagged them on its first live run (Schema Drift run 34752262572, 13/09/2026).
--
-- Every definition below was read from the live catalog on 13/09/2026: column
-- types and defaults, constraint, index and trigger names, and policy predicates
-- match production exactly.
--
-- Idempotent by construction. Against production every statement is a no-op:
-- types, tables, indexes and policies are guarded by existence checks, triggers
-- use CREATE OR REPLACE TRIGGER, and the three trigger functions are replaced
-- with bodies identical to the live ones. Against a fresh database it builds the
-- same objects.

-- ── Shared type and trigger functions ───────────────────────────────────────

do $$
begin
  if not exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public' and t.typname = 'placecard_stage'
  ) then
    create type public.placecard_stage as enum
      ('spark', 'grill', 'shape', 'spec', 'bet', 'graduated', 'parked');
  end if;
end $$;

create or replace function public.update_updated_at_column()
returns trigger
language plpgsql
as $function$
begin
  new.updated_at = now();
  return new;
end $function$;

create or replace function public.set_placecards_updated_at()
returns trigger
language plpgsql
as $function$
begin
  new.updated_at = now();
  return new;
end $function$;

create or replace function public.block_done_with_unverified_promises()
returns trigger
language plpgsql
as $function$
begin
  if new.status = 'done' and exists (
    select 1
    from placecard_promises pp
    where pp.placecard_id = new.placecard_id
      and pp.verified = false
  ) then
    raise exception 'goal card cannot be done: unverified promises exist on placecard %',
      new.placecard_id;
  end if;
  return new;
end $function$;

-- ── Placecards ──────────────────────────────────────────────────────────────

create table if not exists public.placecards (
  id uuid not null default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  title text not null,
  one_liner text,
  end_customer text,
  problem_statement text,
  success_metric text,
  appetite text,
  stage public.placecard_stage not null default 'spark'::public.placecard_stage,
  decision text,
  decision_reason text,
  graduated_repo_url text,
  graduated_linear_project_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint placecards_pkey primary key (id),
  constraint placecards_owner_id_fkey foreign key (owner_id) references auth.users (id),
  constraint placecards_appetite_check check (appetite in ('small_batch', 'big_batch')),
  constraint placecards_decision_check check (decision in ('go', 'park'))
);
create index if not exists idx_placecards_owner_stage on public.placecards (owner_id, stage);
create or replace trigger trg_placecards_updated_at
  before update on public.placecards
  for each row execute function public.set_placecards_updated_at();

create table if not exists public.placecard_artifacts (
  id uuid not null default gen_random_uuid(),
  placecard_id uuid not null,
  kind text not null,
  title text not null,
  content jsonb not null,
  created_by text not null,
  agent_name text,
  created_at timestamptz not null default now(),
  constraint placecard_artifacts_pkey primary key (id),
  constraint placecard_artifacts_placecard_id_fkey foreign key (placecard_id)
    references public.placecards (id) on delete cascade,
  constraint placecard_artifacts_created_by_check check (created_by in ('human', 'agent')),
  constraint placecard_artifacts_kind_check check (kind in (
    'excalidraw_scene', 'gherkin_spec', 'schema_draft', 'c4_context', 'research_note', 'compiled_brief'))
);
create index if not exists idx_artifacts_placecard_kind on public.placecard_artifacts (placecard_id, kind);

create table if not exists public.placecard_boundaries (
  id uuid not null default gen_random_uuid(),
  placecard_id uuid not null,
  kind text not null,
  description text not null,
  created_at timestamptz not null default now(),
  constraint placecard_boundaries_pkey primary key (id),
  constraint placecard_boundaries_placecard_id_fkey foreign key (placecard_id)
    references public.placecards (id) on delete cascade,
  constraint placecard_boundaries_kind_check check (kind in ('must_have', 'rabbit_hole', 'no_go'))
);
create index if not exists idx_boundaries_placecard on public.placecard_boundaries (placecard_id);

create table if not exists public.placecard_goal_cards (
  id uuid not null default gen_random_uuid(),
  placecard_id uuid not null,
  objective text not null,
  output text not null,
  done_when jsonb not null default '[]'::jsonb,
  stages jsonb not null default '[]'::jsonb,
  turn_cap integer not null default 30,
  cost_cap_usd numeric(8,2),
  sandbox text not null,
  surface text not null default 'mission_control_dashboard',
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  linear_issue_id text,
  constraint placecard_goal_cards_pkey primary key (id),
  constraint placecard_goal_cards_placecard_id_fkey foreign key (placecard_id)
    references public.placecards (id) on delete cascade,
  constraint placecard_goal_cards_status_check check (status in ('draft', 'armed', 'running', 'done', 'stopped'))
);
create index if not exists idx_goal_cards_placecard_status on public.placecard_goal_cards (placecard_id, status);
create or replace trigger trg_goal_cards_updated_at
  before update on public.placecard_goal_cards
  for each row execute function public.set_placecards_updated_at();
create or replace trigger trg_block_done_unverified
  before update of status on public.placecard_goal_cards
  for each row execute function public.block_done_with_unverified_promises();

create table if not exists public.placecard_grill_rounds (
  id uuid not null default gen_random_uuid(),
  placecard_id uuid not null,
  round_number integer not null,
  question text not null,
  answer text,
  asked_at timestamptz not null default now(),
  answered_at timestamptz,
  constraint placecard_grill_rounds_pkey primary key (id),
  constraint placecard_grill_rounds_placecard_id_fkey foreign key (placecard_id)
    references public.placecards (id) on delete cascade
);
create index if not exists idx_grill_rounds_placecard on public.placecard_grill_rounds (placecard_id);

create table if not exists public.placecard_promises (
  id uuid not null default gen_random_uuid(),
  placecard_id uuid not null,
  source text not null,
  claim text not null,
  source_url text,
  promised_at date,
  verified boolean not null default false,
  verification_note text,
  created_at timestamptz not null default now(),
  constraint placecard_promises_pkey primary key (id),
  constraint placecard_promises_placecard_id_fkey foreign key (placecard_id)
    references public.placecards (id) on delete cascade,
  constraint placecard_promises_source_check check (source in (
    'campaign', 'website', 'marketing', 'sales', 'docs', 'other'))
);
create index if not exists idx_promises_placecard_verified on public.placecard_promises (placecard_id, verified);

create table if not exists public.placecard_stage_transitions (
  id uuid not null default gen_random_uuid(),
  placecard_id uuid not null,
  from_stage public.placecard_stage,
  to_stage public.placecard_stage not null,
  note text,
  moved_at timestamptz not null default now(),
  constraint placecard_stage_transitions_pkey primary key (id),
  constraint placecard_stage_transitions_placecard_id_fkey foreign key (placecard_id)
    references public.placecards (id) on delete cascade
);
create index if not exists idx_transitions_placecard on public.placecard_stage_transitions (placecard_id);

create table if not exists public.goal_card_runs (
  id uuid not null default gen_random_uuid(),
  goal_card_id uuid not null,
  harness text not null,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  turns_used integer,
  cost_usd numeric(8,2),
  outcome text,
  evidence jsonb not null default '[]'::jsonb,
  note text,
  constraint goal_card_runs_pkey primary key (id),
  constraint goal_card_runs_goal_card_id_fkey foreign key (goal_card_id)
    references public.placecard_goal_cards (id) on delete cascade,
  constraint goal_card_runs_outcome_check check (outcome in (
    'done', 'turn_cap_hit', 'cost_cap_hit', 'stuck', 'stopped_by_human'))
);
create index if not exists idx_runs_goal_card on public.goal_card_runs (goal_card_id);

-- ── Coaching ────────────────────────────────────────────────────────────────

create table if not exists public.coaching_engagements (
  id uuid not null default gen_random_uuid(),
  founder_id uuid not null,
  client_id uuid not null,
  business_name text not null,
  client_name text not null,
  status text not null default 'active',
  consent_given boolean not null default false,
  consent_date date,
  consent_method text,
  consent_disclosure text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coaching_engagements_pkey primary key (id),
  constraint coaching_engagements_founder_fk foreign key (founder_id) references auth.users (id),
  constraint coaching_engagements_status_check check (status in ('active', 'paused', 'completed', 'archived')),
  constraint coaching_engagements_consent_method_check check (consent_method in (
    'written', 'email', 'verbal_recorded', 'in_person_signed')),
  constraint coaching_engagements_consent_complete check (
    consent_given = false or (consent_date is not null and consent_method is not null))
);
create unique index if not exists idx_coaching_engagements_client
  on public.coaching_engagements (founder_id, client_id);
create index if not exists idx_coaching_engagements_sort
  on public.coaching_engagements (founder_id, business_name, client_name);
create or replace trigger coaching_engagements_updated_at
  before update on public.coaching_engagements
  for each row execute function public.update_updated_at_column();

create table if not exists public.coaching_sessions (
  id uuid not null default gen_random_uuid(),
  founder_id uuid not null,
  engagement_id uuid not null,
  client_id uuid not null,
  session_date date not null default current_date,
  session_number integer,
  duration_minutes integer,
  source text not null default 'paste',
  source_ref text,
  transcript text,
  status text not null default 'captured',
  error_message text,
  model text,
  input_tokens integer,
  output_tokens integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coaching_sessions_pkey primary key (id),
  constraint coaching_sessions_engagement_fk foreign key (engagement_id)
    references public.coaching_engagements (id) on delete cascade,
  constraint coaching_sessions_source_check check (source in ('plaud', 'upload', 'paste', 'live')),
  constraint coaching_sessions_status_check check (status in (
    'captured', 'extracting', 'extracted', 'reviewed', 'failed'))
);
create index if not exists idx_coaching_sessions_engagement
  on public.coaching_sessions (engagement_id, session_date desc);
create or replace trigger coaching_sessions_updated_at
  before update on public.coaching_sessions
  for each row execute function public.update_updated_at_column();

create table if not exists public.coaching_extractions (
  id uuid not null default gen_random_uuid(),
  founder_id uuid not null,
  engagement_id uuid not null,
  session_id uuid not null,
  client_id uuid not null,
  kind text not null,
  body text not null,
  owner text,
  due_date date,
  metric_value text,
  metric_unit text,
  metric_period text,
  transcript_quote text,
  transcript_offset integer,
  confidence numeric(3,2),
  status text not null default 'proposed',
  original_body text,
  reviewed_at timestamptz,
  valid_from date not null default current_date,
  superseded_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coaching_extractions_pkey primary key (id),
  constraint coaching_extractions_engagement_fk foreign key (engagement_id)
    references public.coaching_engagements (id) on delete cascade,
  constraint coaching_extractions_session_fk foreign key (session_id)
    references public.coaching_sessions (id) on delete cascade,
  constraint coaching_extractions_superseded_fk foreign key (superseded_by)
    references public.coaching_extractions (id) on delete set null,
  constraint coaching_extractions_confidence_check check (confidence >= 0 and confidence <= 1),
  constraint coaching_extractions_kind_check check (kind in (
    'want', 'need', 'requirement', 'commitment', 'metric', 'blocker', 'decision', 'open_question')),
  constraint coaching_extractions_owner_check check (owner in ('coach', 'client')),
  constraint coaching_extractions_status_check check (status in (
    'proposed', 'approved', 'rejected', 'superseded', 'done'))
);
create index if not exists idx_coaching_extractions_engagement
  on public.coaching_extractions (engagement_id, kind, status);
create index if not exists idx_coaching_extractions_open
  on public.coaching_extractions (engagement_id, valid_from)
  where status = 'approved' and superseded_by is null;
create index if not exists idx_coaching_extractions_session
  on public.coaching_extractions (session_id);
create or replace trigger coaching_extractions_updated_at
  before update on public.coaching_extractions
  for each row execute function public.update_updated_at_column();

-- ── Lead verifications ──────────────────────────────────────────────────────

create table if not exists public.lead_verifications (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  email_address text not null,
  company_domain text not null,
  verification_status text not null,
  compliance_token text not null,
  latency_ms integer not null,
  created_at timestamptz not null default timezone('utc'::text, now()),
  constraint lead_verifications_pkey primary key (id),
  constraint lead_verifications_compliance_token_key unique (compliance_token),
  constraint lead_verifications_verification_status_check check (verification_status in (
    'verified', 'flagged', 'purged'))
);
create index if not exists idx_lead_verifications_user_status
  on public.lead_verifications (user_id, verification_status);

-- ── Row level security (all 12 tables: RLS on, not forced, one policy each) ──

alter table public.placecards enable row level security;
alter table public.placecard_artifacts enable row level security;
alter table public.placecard_boundaries enable row level security;
alter table public.placecard_goal_cards enable row level security;
alter table public.placecard_grill_rounds enable row level security;
alter table public.placecard_promises enable row level security;
alter table public.placecard_stage_transitions enable row level security;
alter table public.goal_card_runs enable row level security;
alter table public.coaching_engagements enable row level security;
alter table public.coaching_sessions enable row level security;
alter table public.coaching_extractions enable row level security;
alter table public.lead_verifications enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecards' and policyname = 'placecards_owner_all') then
    create policy placecards_owner_all on public.placecards for all
      using (auth.uid() = owner_id) with check (auth.uid() = owner_id);
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecard_artifacts' and policyname = 'artifacts_owner_all') then
    create policy artifacts_owner_all on public.placecard_artifacts for all
      using (exists (select 1 from placecards p
                     where p.id = placecard_artifacts.placecard_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecards p
                          where p.id = placecard_artifacts.placecard_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecard_boundaries' and policyname = 'boundaries_owner_all') then
    create policy boundaries_owner_all on public.placecard_boundaries for all
      using (exists (select 1 from placecards p
                     where p.id = placecard_boundaries.placecard_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecards p
                          where p.id = placecard_boundaries.placecard_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecard_goal_cards' and policyname = 'goal_cards_owner_all') then
    create policy goal_cards_owner_all on public.placecard_goal_cards for all
      using (exists (select 1 from placecards p
                     where p.id = placecard_goal_cards.placecard_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecards p
                          where p.id = placecard_goal_cards.placecard_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecard_grill_rounds' and policyname = 'grill_rounds_owner_all') then
    create policy grill_rounds_owner_all on public.placecard_grill_rounds for all
      using (exists (select 1 from placecards p
                     where p.id = placecard_grill_rounds.placecard_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecards p
                          where p.id = placecard_grill_rounds.placecard_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecard_promises' and policyname = 'promises_owner_all') then
    create policy promises_owner_all on public.placecard_promises for all
      using (exists (select 1 from placecards p
                     where p.id = placecard_promises.placecard_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecards p
                          where p.id = placecard_promises.placecard_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'placecard_stage_transitions' and policyname = 'transitions_owner_all') then
    create policy transitions_owner_all on public.placecard_stage_transitions for all
      using (exists (select 1 from placecards p
                     where p.id = placecard_stage_transitions.placecard_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecards p
                          where p.id = placecard_stage_transitions.placecard_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'goal_card_runs' and policyname = 'runs_owner_all') then
    create policy runs_owner_all on public.goal_card_runs for all
      using (exists (select 1 from placecard_goal_cards g join placecards p on p.id = g.placecard_id
                     where g.id = goal_card_runs.goal_card_id and p.owner_id = auth.uid()))
      with check (exists (select 1 from placecard_goal_cards g join placecards p on p.id = g.placecard_id
                          where g.id = goal_card_runs.goal_card_id and p.owner_id = auth.uid()));
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'coaching_engagements' and policyname = 'founder_only') then
    create policy founder_only on public.coaching_engagements for all
      using (founder_id = auth.uid());
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'coaching_sessions' and policyname = 'founder_only') then
    create policy founder_only on public.coaching_sessions for all
      using (founder_id = auth.uid());
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'coaching_extractions' and policyname = 'founder_only') then
    create policy founder_only on public.coaching_extractions for all
      using (founder_id = auth.uid());
  end if;

  if not exists (select 1 from pg_policies where schemaname = 'public'
                 and tablename = 'lead_verifications'
                 and policyname = 'Enforce organization boundary isolation') then
    create policy "Enforce organization boundary isolation" on public.lead_verifications
      for all to authenticated
      using (auth.uid() = user_id) with check (auth.uid() = user_id);
  end if;
end $$;
