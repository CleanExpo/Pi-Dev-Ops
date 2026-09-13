-- Back-fill PlaceCard + lead_verifications tables that are live in Pi CEO
-- and declared nowhere in this repo (Schema Drift 34752262572, 2026-09-13).
--
-- THIS FILE DESCRIBES PRODUCTION; IT DID NOT CREATE IT. Every statement is
-- IF NOT EXISTS / DROP IF EXISTS and is a no-op against the live database.
-- Its purpose is the CI shadow database so rls-assertions can see these
-- tables. No file in CleanExpo (Pi-Dev-Ops, Unite-Group, Synthex,
-- RestoreAssist, …) authored this schema — it was created out of band.
--
-- SOURCE. Column names and types were recovered from the live PostgREST
-- API on zbryrmxmgfmslqzizsto with the public anon key (already in
-- dashboard/index.html). A column is listed only when `GET /{table}?select=`
-- returned 200; types come from filter errors (`invalid input syntax for
-- type uuid|timestamptz|numeric|boolean|json` / `enum placecard_stage`).
-- Extra name sweeps found no further columns beyond those below.
--
-- ENUM. `placecards.stage` and the transition columns are live type
-- `placecard_stage`. Confirmed values: spark, grill. Other labels in a
-- 150-word sweep were rejected. CREATE TYPE is skipped when the type
-- already exists, so extra live values are not clobbered.
--
-- RLS. These tables have no policy dump and no in-repo consumer. Policies
-- follow the owner-scoped sibling pattern (cc_* founder_id, coaching
-- founder_only): parent keyed on owner_id / user_id = auth.uid(); children
-- via the parent row. Inventing USING (true) would be wider than every
-- sibling; leaving RLS on with no policy would deny everyone, including
-- the service role — the state rls_coverage.sql exists to catch.

do $$
begin
  if not exists (select 1 from pg_type where typname = 'placecard_stage') then
    create type public.placecard_stage as enum ('spark', 'grill');
  end if;
end $$;

-- ── parent ──────────────────────────────────────────────────────────────────

create table if not exists public.placecards (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id),
  title text,
  one_liner text,
  stage public.placecard_stage,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.placecards enable row level security;

drop policy if exists "owner_only" on public.placecards;
create policy "owner_only" on public.placecards
  for all using (owner_id = auth.uid());

create index if not exists placecards_owner_id_idx
  on public.placecards (owner_id);

-- ── children ────────────────────────────────────────────────────────────────

create table if not exists public.placecard_artifacts (
  id uuid primary key default gen_random_uuid(),
  placecard_id uuid not null references public.placecards(id) on delete cascade,
  title text,
  kind text,
  content jsonb,
  created_by text,
  created_at timestamptz not null default now()
);

create table if not exists public.placecard_boundaries (
  id uuid primary key default gen_random_uuid(),
  placecard_id uuid not null references public.placecards(id) on delete cascade,
  kind text,
  description text,
  created_at timestamptz not null default now()
);

create table if not exists public.placecard_goal_cards (
  id uuid primary key default gen_random_uuid(),
  placecard_id uuid not null references public.placecards(id) on delete cascade,
  status text,
  output text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.placecard_grill_rounds (
  id uuid primary key default gen_random_uuid(),
  placecard_id uuid not null references public.placecards(id) on delete cascade,
  round_number integer,
  question text,
  answer text
);

create table if not exists public.placecard_promises (
  id uuid primary key default gen_random_uuid(),
  placecard_id uuid not null references public.placecards(id) on delete cascade,
  source text,
  verified boolean,
  created_at timestamptz not null default now()
);

create table if not exists public.placecard_stage_transitions (
  id uuid primary key default gen_random_uuid(),
  placecard_id uuid not null references public.placecards(id) on delete cascade,
  from_stage public.placecard_stage,
  to_stage public.placecard_stage
);

create table if not exists public.goal_card_runs (
  id uuid primary key default gen_random_uuid(),
  goal_card_id uuid not null
    references public.placecard_goal_cards(id) on delete cascade,
  started_at timestamptz,
  ended_at timestamptz,
  cost_usd numeric
);

create table if not exists public.lead_verifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  verification_status text,
  created_at timestamptz not null default now()
);

-- ── indexes ─────────────────────────────────────────────────────────────────

create index if not exists placecard_artifacts_placecard_id_idx
  on public.placecard_artifacts (placecard_id);
create index if not exists placecard_boundaries_placecard_id_idx
  on public.placecard_boundaries (placecard_id);
create index if not exists placecard_goal_cards_placecard_id_idx
  on public.placecard_goal_cards (placecard_id);
create index if not exists placecard_grill_rounds_placecard_id_idx
  on public.placecard_grill_rounds (placecard_id);
create index if not exists placecard_promises_placecard_id_idx
  on public.placecard_promises (placecard_id);
create index if not exists placecard_stage_transitions_placecard_id_idx
  on public.placecard_stage_transitions (placecard_id);
create index if not exists goal_card_runs_goal_card_id_idx
  on public.goal_card_runs (goal_card_id);
create index if not exists lead_verifications_user_id_idx
  on public.lead_verifications (user_id);

-- ── RLS ─────────────────────────────────────────────────────────────────────

alter table public.placecard_artifacts          enable row level security;
alter table public.placecard_boundaries         enable row level security;
alter table public.placecard_goal_cards         enable row level security;
alter table public.placecard_grill_rounds       enable row level security;
alter table public.placecard_promises           enable row level security;
alter table public.placecard_stage_transitions  enable row level security;
alter table public.goal_card_runs               enable row level security;
alter table public.lead_verifications           enable row level security;

drop policy if exists "via_parent" on public.placecard_artifacts;
create policy "via_parent" on public.placecard_artifacts for all
  using (exists (
    select 1 from public.placecards p
    where p.id = placecard_id and p.owner_id = auth.uid()
  ));

drop policy if exists "via_parent" on public.placecard_boundaries;
create policy "via_parent" on public.placecard_boundaries for all
  using (exists (
    select 1 from public.placecards p
    where p.id = placecard_id and p.owner_id = auth.uid()
  ));

drop policy if exists "via_parent" on public.placecard_goal_cards;
create policy "via_parent" on public.placecard_goal_cards for all
  using (exists (
    select 1 from public.placecards p
    where p.id = placecard_id and p.owner_id = auth.uid()
  ));

drop policy if exists "via_parent" on public.placecard_grill_rounds;
create policy "via_parent" on public.placecard_grill_rounds for all
  using (exists (
    select 1 from public.placecards p
    where p.id = placecard_id and p.owner_id = auth.uid()
  ));

drop policy if exists "via_parent" on public.placecard_promises;
create policy "via_parent" on public.placecard_promises for all
  using (exists (
    select 1 from public.placecards p
    where p.id = placecard_id and p.owner_id = auth.uid()
  ));

drop policy if exists "via_parent" on public.placecard_stage_transitions;
create policy "via_parent" on public.placecard_stage_transitions for all
  using (exists (
    select 1 from public.placecards p
    where p.id = placecard_id and p.owner_id = auth.uid()
  ));

drop policy if exists "via_goal_card" on public.goal_card_runs;
create policy "via_goal_card" on public.goal_card_runs for all
  using (exists (
    select 1
      from public.placecard_goal_cards g
      join public.placecards p on p.id = g.placecard_id
     where g.id = goal_card_id and p.owner_id = auth.uid()
  ));

drop policy if exists "owner_only" on public.lead_verifications;
create policy "owner_only" on public.lead_verifications
  for all using (user_id = auth.uid());
