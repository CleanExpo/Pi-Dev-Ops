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
