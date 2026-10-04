-- Nexus Mesh 0004 — per-lane events from the mc-lane Claude Code mod.
--
-- Spec: docs/specs/claude-mods-integration.md §3.1.
-- Writer: POST /api/mesh/lane-events (app/server/routes/mesh_lane_events.py),
-- the only writer, as with every mesh_* table (RLS: service role only).
--
-- Additive: a new table, nothing existing changes. The server can deploy
-- before this is applied — the POST then answers 502 and the mod keeps its
-- queue (it never drops events on a failed write).
--
-- Numbering: check production's migration ledger for a `nexus_mesh_0004*`
-- entry before applying (0003's header: the ledger holds a 0002 with no file
-- here). Rename this file if 0004 is taken.
--
-- No free text: every text column is validated against a pattern by the
-- route before insert (tool name, owner/name, model id, session id, host).

create table if not exists mesh_lane_events (
  id          bigint generated always as identity primary key,
  host        text not null,
  session_id  text not null,
  seq         bigint not null,
  kind        text not null check (kind in ('session_start','tool','usage','session_end')),
  at          text not null,                -- the lane's own clock, ISO-8601 as sent
  received_at timestamptz not null default now(),
  repo        text,
  model       text,
  tool        text,
  ok          boolean,
  ms          double precision,
  ctx_pct     double precision,
  rate_pct    double precision,
  cost_usd    double precision,             -- NULL = unknown; never read as 0
  unique (session_id, seq)
);

create index if not exists mesh_lane_events_session on mesh_lane_events (session_id, id);
create index if not exists mesh_lane_events_host_recent on mesh_lane_events (host, received_at desc);

alter table mesh_lane_events enable row level security;
drop policy if exists "service_only" on mesh_lane_events;
create policy "service_only" on mesh_lane_events for all to service_role using (true);
