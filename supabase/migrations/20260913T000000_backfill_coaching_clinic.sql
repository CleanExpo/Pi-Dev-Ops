-- Back-fill the three coaching_* tables that are live in Pi CEO and declared
-- nowhere in this repo (Schema Drift 34752262572, 2026-09-13).
--
-- THIS FILE DESCRIBES PRODUCTION; IT DID NOT CREATE IT. The tables already
-- exist in the Pi CEO project. Every statement is IF NOT EXISTS / DROP IF
-- EXISTS and is a no-op against that database. Its purpose is the CI shadow
-- database: rls-assertions can only see what this repo declares.
--
-- SOURCE. Columns, checks, indexes, founder-only policies, and the consent
-- trigger are taken from CleanExpo/Unite-Group
-- apps/web/supabase/migrations/20260907180000_coaching_engagements.sql —
-- the file that authored the clinic — then confirmed live on
-- zbryrmxmgfmslqzizsto via PostgREST (every named column returned 200).
--
-- ADAPTATIONS, each forced by what is true in THIS repo's shadow database,
-- not by taste:
--   * No FK to public.crm_contacts. That table is not in Pi CEO (PostgREST
--     404 / PGRST205; also absent from the live-not-declared list, so it is
--     not merely hidden from the API). The Unite-Group file's composite
--     unique on crm_contacts and the three client_founder FKs are therefore
--     omitted. client_id stays as uuid not null.
--   * No updated_at triggers. public.update_updated_at_column() is a
--     Unite-Group house function and does not exist here.
--
-- OWNERSHIP. Nothing in Pi-Dev-Ops reads or writes these tables. They are
-- declared for gate coverage. The clinic lives in Unite-Group.

-- ── 1. Engagements ──────────────────────────────────────────────────────────

create table if not exists public.coaching_engagements (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references auth.users(id),
  client_id uuid not null,
  business_name text not null,
  client_name text not null,
  status text not null default 'active'
    check (status in ('active', 'paused', 'completed', 'archived')),
  consent_given boolean not null default false,
  consent_date date,
  consent_method text check (consent_method in (
    'written', 'email', 'verbal_recorded', 'in_person_signed'
  )),
  consent_disclosure text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coaching_engagements_consent_complete
    check (
      consent_given = false
      or (
        consent_date is not null
        and consent_method is not null
        and consent_disclosure ~ '[^[:space:]]'
      )
    )
);

alter table public.coaching_engagements enable row level security;

drop policy if exists "founder_only" on public.coaching_engagements;
create policy "founder_only" on public.coaching_engagements
  for all using (founder_id = auth.uid());

create unique index if not exists idx_coaching_engagements_client
  on public.coaching_engagements(founder_id, client_id);
create unique index if not exists coaching_engagements_id_founder_key
  on public.coaching_engagements(id, founder_id);
create index if not exists idx_coaching_engagements_sort
  on public.coaching_engagements(founder_id, business_name, client_name);

-- ── 2. Sessions ─────────────────────────────────────────────────────────────

create table if not exists public.coaching_sessions (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references auth.users(id),
  engagement_id uuid not null,
  client_id uuid not null,
  session_date date not null default current_date,
  session_number integer,
  duration_minutes integer,
  source text not null default 'paste'
    check (source in ('plaud', 'upload', 'paste', 'live')),
  source_ref text,
  transcript text,
  status text not null default 'captured'
    check (status in ('captured', 'extracting', 'extracted', 'reviewed', 'failed')),
  error_message text,
  model text,
  input_tokens integer,
  output_tokens integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coaching_sessions_engagement_founder_fkey
    foreign key (engagement_id, founder_id)
    references public.coaching_engagements(id, founder_id) on delete cascade,
  constraint coaching_sessions_source_ref_nonempty
    check (source_ref is null or nullif(btrim(source_ref), '') is not null),
  constraint coaching_sessions_founder_source_ref_key
    unique (founder_id, source_ref)
);

alter table public.coaching_sessions enable row level security;

drop policy if exists "founder_only" on public.coaching_sessions;
create policy "founder_only" on public.coaching_sessions
  for all using (founder_id = auth.uid());

create index if not exists idx_coaching_sessions_engagement
  on public.coaching_sessions(engagement_id, session_date desc);
create unique index if not exists coaching_sessions_id_founder_key
  on public.coaching_sessions(id, founder_id);

-- ── 3. Extractions ──────────────────────────────────────────────────────────

create table if not exists public.coaching_extractions (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references auth.users(id),
  engagement_id uuid not null,
  session_id uuid not null,
  client_id uuid not null,
  kind text not null check (kind in (
    'want', 'need', 'requirement', 'commitment',
    'metric', 'blocker', 'decision', 'open_question'
  )),
  body text not null,
  owner text check (owner in ('coach', 'client')),
  due_date date,
  metric_value text,
  metric_unit text,
  metric_period text,
  transcript_quote text,
  transcript_offset integer,
  confidence numeric(3, 2) check (confidence >= 0 and confidence <= 1),
  status text not null default 'proposed'
    check (status in ('proposed', 'approved', 'rejected', 'superseded', 'done')),
  original_body text,
  reviewed_at timestamptz,
  valid_from date not null default current_date,
  superseded_by uuid references public.coaching_extractions(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coaching_extractions_engagement_founder_fkey
    foreign key (engagement_id, founder_id)
    references public.coaching_engagements(id, founder_id) on delete cascade,
  constraint coaching_extractions_session_founder_fkey
    foreign key (session_id, founder_id)
    references public.coaching_sessions(id, founder_id) on delete cascade
);

alter table public.coaching_extractions enable row level security;

drop policy if exists "founder_only" on public.coaching_extractions;
create policy "founder_only" on public.coaching_extractions
  for all using (founder_id = auth.uid());

create index if not exists idx_coaching_extractions_engagement
  on public.coaching_extractions(engagement_id, kind, status);
create index if not exists idx_coaching_extractions_session
  on public.coaching_extractions(session_id);
create index if not exists idx_coaching_extractions_open
  on public.coaching_extractions(engagement_id, valid_from)
  where status = 'approved' and superseded_by is null;

-- Consent must be true on the parent engagement before a session can land.
-- Same function as Unite-Group; it only touches coaching_* tables.

create or replace function public.enforce_coaching_session_consent()
returns trigger
language plpgsql
as $$
declare
  engagement_consent boolean;
begin
  select consent_given
    into engagement_consent
    from public.coaching_engagements
   where id = new.engagement_id
     and founder_id = new.founder_id
   for share;

  if not found or engagement_consent is not true then
    raise exception 'coaching session requires active consent'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists coaching_sessions_consent on public.coaching_sessions;
create trigger coaching_sessions_consent
  before insert on public.coaching_sessions
  for each row execute function public.enforce_coaching_session_consent();
