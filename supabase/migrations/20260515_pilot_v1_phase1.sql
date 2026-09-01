-- Pilot V1 Phase 1 schema — create pilot_suggestions/preferences/messages from scratch.
--
-- Per ADR 001: pillar text[] NOT NULL with GIN index.
-- Per ADR 002: tenant_slug NOT NULL + RLS via current_setting on all 3 tables.
-- Per ADR 003: pause_state CHECK constraint + pilot_suggestion_messages for editMessageReplyMarkup.
-- Per ADR 004 §1: set_app_tenant(slug text) function — security definer,
--   revoke from public, grant execute to authenticated + service_role.
--
-- Rollback (exact order):
--   drop table if exists public.pilot_suggestion_messages;
--   drop table if exists public.pilot_preferences;
--   drop table if exists public.pilot_suggestions;
--   drop function if exists public.set_app_tenant(text);

-- ── pilot_suggestions ────────────────────────────────────────────────────────
create table if not exists public.pilot_suggestions (
  id            bigserial    primary key,
  fingerprint   text         not null,
  headline      text         not null,
  pillar        text[]       not null,
  effort        text         not null check (effort in ('XS','S','M','L','XL')),
  source        text         not null,
  confidence    text         not null check (confidence in ('LOW','MEDIUM','HIGH')),
  body_json     jsonb        not null default '{}'::jsonb,
  state         text         not null default 'pending'
                             check (state in ('pending','dismissed','snoozed','done','never')),
  tenant_slug   text         not null,
  created_at    timestamptz  not null default now()
);

create index if not exists pilot_suggestions_tenant_idx
  on public.pilot_suggestions (tenant_slug);
create index if not exists pilot_suggestions_pillar_gin_idx
  on public.pilot_suggestions using gin (pillar);

alter table public.pilot_suggestions enable row level security;
-- RA-7397: drop-then-create, matching every later migration in this repo
-- (20260512_aip_core.sql, mesh/schema/0001_nexus_mesh.sql). The tables and
-- indexes above are already `if not exists`; a bare `create policy` was the one
-- statement that could not be re-applied, so this file errored against any
-- already-migrated database. Semantically identical on a fresh apply -- the
-- drop is a no-op -- so the resulting schema is unchanged.
drop policy if exists tenant_isolation_pilot_suggestions on public.pilot_suggestions;
create policy tenant_isolation_pilot_suggestions
  on public.pilot_suggestions
  using (tenant_slug = current_setting('app.current_tenant_slug', true));

-- ── pilot_preferences ────────────────────────────────────────────────────────
create table if not exists public.pilot_preferences (
  id                  bigserial    primary key,
  tenant_slug         text         not null,
  fingerprint_pattern text         not null,
  rule                text         not null check (rule in ('never','snooze','always')),
  pause_state         text         not null default 'active'
                                   check (
                                     pause_state = 'active'
                                     or pause_state = 'paused-hard'
                                     or pause_state like 'paused-until-%'
                                   ),
  created_at          timestamptz  not null default now(),
  unique (tenant_slug, fingerprint_pattern)
);

alter table public.pilot_preferences enable row level security;
drop policy if exists tenant_isolation_pilot_preferences on public.pilot_preferences;
create policy tenant_isolation_pilot_preferences
  on public.pilot_preferences
  using (tenant_slug = current_setting('app.current_tenant_slug', true));

-- ── pilot_suggestion_messages ────────────────────────────────────────────────
create table if not exists public.pilot_suggestion_messages (
  id             bigserial    primary key,
  suggestion_id  bigint       not null unique
                              references public.pilot_suggestions(id) on delete cascade,
  chat_id        bigint       not null,
  message_id     bigint       not null,
  tenant_slug    text         not null,
  created_at     timestamptz  not null default now()
);

alter table public.pilot_suggestion_messages enable row level security;
drop policy if exists tenant_isolation_pilot_suggestion_messages on public.pilot_suggestion_messages;
create policy tenant_isolation_pilot_suggestion_messages
  on public.pilot_suggestion_messages
  using (tenant_slug = current_setting('app.current_tenant_slug', true));

-- ── set_app_tenant function ───────────────────────────────────────────────────
create or replace function public.set_app_tenant(slug text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  perform set_config('app.current_tenant_slug', slug, true);
end;
$$;

-- Revoke from public, grant only to authenticated + service_role.
revoke all on function public.set_app_tenant(text) from public;
grant execute on function public.set_app_tenant(text) to authenticated;
grant execute on function public.set_app_tenant(text) to service_role;
