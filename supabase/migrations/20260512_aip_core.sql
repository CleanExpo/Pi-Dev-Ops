-- AIP Day-1 — core ontology tables.
-- Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 1 "Ontology primitives".
-- Three-table base: entities + relationships + action log. jsonb properties for portability.
-- RLS enabled; starter policy is intentionally coarse — per-permission gates land Day-3
-- when the action runtime is wired and `aip_grants` is in scope (see § "Permission model").

create table if not exists aip_entities (
  uri          text primary key,
  kind         text not null,
  id           text not null,
  properties   jsonb not null default '{}'::jsonb,
  source       jsonb not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (kind, id)
);
create index if not exists aip_entities_kind_idx on aip_entities (kind);
create index if not exists aip_entities_props_gin on aip_entities using gin (properties jsonb_path_ops);

create table if not exists aip_relationships (
  uri          text primary key,
  kind         text not null,
  from_uri     text not null references aip_entities(uri) on delete cascade,
  to_uri       text not null references aip_entities(uri) on delete cascade,
  cardinality  text not null check (cardinality in ('1:1','N:1','1:N','N:N')),
  properties   jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  unique (kind, from_uri, to_uri)
);
create index if not exists aip_rel_from_idx on aip_relationships (from_uri, kind);
create index if not exists aip_rel_to_idx   on aip_relationships (to_uri, kind);

create table if not exists aip_action_log (
  id           bigserial primary key,
  action       text not null,
  actor        text not null,
  params       jsonb not null,
  permission   text not null,
  affected     text[] not null,
  before_hash  text,
  after_hash   text,
  result       jsonb,
  error        text,
  started_at   timestamptz not null,
  ended_at     timestamptz
);
create index if not exists aip_action_log_actor_idx on aip_action_log (actor, started_at desc);

-- Row-level security.
-- Day-1 starter: authenticated users may read all rows; only the service_role may write.
-- Day-3 will replace these with per-permission policies driven by JWT claims and
-- (eventually) the aip_grants table documented in the schema page as the upgrade path.
alter table aip_entities      enable row level security;
alter table aip_relationships enable row level security;
alter table aip_action_log    enable row level security;

-- aip_entities
drop policy if exists aip_entities_read on aip_entities;
create policy aip_entities_read on aip_entities
  for select
  to authenticated
  using (true);

drop policy if exists aip_entities_write_service on aip_entities;
create policy aip_entities_write_service on aip_entities
  for all
  to service_role
  using (true)
  with check (true);

-- aip_relationships
drop policy if exists aip_relationships_read on aip_relationships;
create policy aip_relationships_read on aip_relationships
  for select
  to authenticated
  using (true);

drop policy if exists aip_relationships_write_service on aip_relationships;
create policy aip_relationships_write_service on aip_relationships
  for all
  to service_role
  using (true)
  with check (true);

-- aip_action_log
-- Reads restricted to the actor themselves OR service_role; writes service_role only.
-- `actor` is stored as a free-form string today (e.g. "agent://pi-ceo/margot",
-- "user:<uuid>"); the auth.uid() comparison is best-effort until Day-3 normalises actors.
drop policy if exists aip_action_log_read_self on aip_action_log;
create policy aip_action_log_read_self on aip_action_log
  for select
  to authenticated
  using (actor = ('user:' || (auth.uid())::text));

drop policy if exists aip_action_log_write_service on aip_action_log;
create policy aip_action_log_write_service on aip_action_log
  for all
  to service_role
  using (true)
  with check (true);
