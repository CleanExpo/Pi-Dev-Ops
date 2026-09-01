-- Nexus Mesh — fleet coordination schema
-- Spec: docs/superpowers/specs/2026-06-11-nexus-mesh-design.md
-- Target: Supabase "Pi CEO" (zbryrmxmgfmslqzizsto). Idempotent; safe to re-run.

-- 1. Machines: one row per fleet node, upserted by the heartbeat daemon every ~20s.
create table if not exists mesh_machines (
  host            text primary key,
  os              text,
  tailnet_ip      text,
  status          text not null default 'online',   -- online | idle | working | offline
  cpu_pct         numeric,
  mem_pct         numeric,
  load1           numeric,
  agent_runtimes  jsonb default '[]'::jsonb,          -- [{runtime, version, present}]
  version         text,
  last_seen       timestamptz not null default now()
);

-- 2. Agents: live agent sessions across the fleet.
create table if not exists mesh_agents (
  id            uuid primary key default gen_random_uuid(),
  machine       text not null references mesh_machines(host) on delete cascade,
  runtime       text not null,                        -- claude | codex | hermes
  session_id    text,
  repo          text,
  branch        text,
  current_task  text,
  state         text not null default 'idle',         -- idle | working | shipping | error
  started_at    timestamptz not null default now(),
  last_ship_at  timestamptz,
  updated_at    timestamptz not null default now(),
  unique (machine, runtime, session_id)
);

-- 3. Ships: the git activity feed — appended after each autogit push.
create table if not exists mesh_ships (
  id             uuid primary key default gen_random_uuid(),
  machine        text not null,
  repo           text not null,
  branch         text,
  sha            text,
  subject        text,
  files_changed  int default 0,
  shipped_at     timestamptz not null default now()
);
create index if not exists mesh_ships_recent on mesh_ships (shipped_at desc);

-- 4. Work claims: atomic Linear-ticket assignment. The partial unique index is the
--    concurrency guard — only ONE open claim per linear_id can exist fleet-wide.
create table if not exists mesh_work_claims (
  id           uuid primary key default gen_random_uuid(),
  linear_id    text not null,
  machine      text references mesh_machines(host) on delete set null,
  branch       text,
  state        text not null default 'claimed',       -- claimed | working | done | released | failed
  claimed_at   timestamptz not null default now(),
  released_at  timestamptz
);
create unique index if not exists mesh_work_claims_one_open
  on mesh_work_claims (linear_id)
  where state in ('claimed', 'working');
create index if not exists mesh_work_claims_machine on mesh_work_claims (machine, state);

-- Fleet view: machines with a live/offline flag (offline = no heartbeat in 60s) + agent count.
create or replace view mesh_fleet as
select
  m.*,
  (now() - m.last_seen) > interval '60 seconds' as is_stale,
  (select count(*) from mesh_agents a where a.machine = m.host and a.state <> 'idle') as active_agents
from mesh_machines m;

-- RLS policies: the design intent ("RLS-locked to service role") — RLS was
-- enabled but no policies existed (advisor rls_enabled_no_policy). service_role
-- bypasses RLS so the server keeps writing either way; these make intent explicit.
--
-- ENABLE COMES FIRST, and did not used to be here at all (RA-7396). The comment
-- above says "RLS was enabled" because it was — in production, already, by hand.
-- This file only added the missing policies, so it was correct solely by virtue
-- of prior state nobody could see from reading it. Applied to a FRESH database
-- it produced these four tables with policies attached and RLS off, which means
-- the policies are inert and the tables are readable by anyone the grants admit.
-- ADR-008 calls this file the mesh schema of record, so a rebuild from it — a
-- new environment, a restore — was silently insecure.
--
-- Caught the first time CI applied this file, by the coverage assertion that
-- had never seen a mesh table before. Idempotent, and a no-op against any
-- database where RLS is already on.
alter table mesh_machines    enable row level security;
alter table mesh_agents      enable row level security;
alter table mesh_ships       enable row level security;
alter table mesh_work_claims enable row level security;

drop policy if exists "service_only" on mesh_machines;
create policy "service_only" on mesh_machines for all to service_role using (true);
drop policy if exists "service_only" on mesh_agents;
create policy "service_only" on mesh_agents for all to service_role using (true);
drop policy if exists "service_only" on mesh_ships;
create policy "service_only" on mesh_ships for all to service_role using (true);
drop policy if exists "service_only" on mesh_work_claims;
create policy "service_only" on mesh_work_claims for all to service_role using (true);
