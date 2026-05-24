-- supabase/tests/pgtap/pilot_v1_isolation.sql
-- Per ADR 002: assert RLS + tenant isolation on every pilot_* table.
-- Direct remediation for [[portfolio-health-snapshot-2026-05-14]] Margot pattern.
-- Run via GitHub Action (pgtap-pilot.yml) on every PR touching swarm/pilot/** or migrations/**.

begin;

do $$
begin
  -- 1. RLS enabled on pilot_suggestions
  if not (
    select c.relrowsecurity
    from pg_class c join pg_namespace n on c.relnamespace = n.oid
    where n.nspname = 'public' and c.relname = 'pilot_suggestions'
  ) then
    raise exception 'RLS not enabled on pilot_suggestions';
  end if;

  -- 2. RLS enabled on pilot_preferences
  if not (
    select c.relrowsecurity
    from pg_class c join pg_namespace n on c.relnamespace = n.oid
    where n.nspname = 'public' and c.relname = 'pilot_preferences'
  ) then
    raise exception 'RLS not enabled on pilot_preferences';
  end if;

  -- 3. RLS enabled on pilot_suggestion_messages
  if not (
    select c.relrowsecurity
    from pg_class c join pg_namespace n on c.relnamespace = n.oid
    where n.nspname = 'public' and c.relname = 'pilot_suggestion_messages'
  ) then
    raise exception 'RLS not enabled on pilot_suggestion_messages';
  end if;

  -- 4. tenant_isolation policy exists on pilot_suggestions
  if not exists(
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'pilot_suggestions'
      and policyname = 'tenant_isolation_pilot_suggestions'
  ) then
    raise exception 'tenant_isolation policy missing on pilot_suggestions';
  end if;

  -- 5. tenant_isolation policy exists on pilot_preferences
  if not exists(
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'pilot_preferences'
      and policyname = 'tenant_isolation_pilot_preferences'
  ) then
    raise exception 'tenant_isolation policy missing on pilot_preferences';
  end if;

  -- 6. tenant_isolation policy exists on pilot_suggestion_messages
  if not exists(
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename  = 'pilot_suggestion_messages'
      and policyname = 'tenant_isolation_pilot_suggestion_messages'
  ) then
    raise exception 'tenant_isolation policy missing on pilot_suggestion_messages';
  end if;

  -- 7. pilot_suggestions.pillar is text[] (array type)
  if not (
    select a.attndims > 0 or t.typcategory = 'A'
    from pg_attribute a
    join pg_class c on a.attrelid = c.oid
    join pg_namespace n on c.relnamespace = n.oid
    join pg_type t on a.atttypid = t.oid
    where n.nspname = 'public'
      and c.relname  = 'pilot_suggestions'
      and a.attname  = 'pillar'
      and a.attnum   > 0
  ) then
    raise exception 'pilot_suggestions.pillar is not an array type';
  end if;

  -- 8. set_app_tenant function exists and is security definer
  if not exists(
    select 1 from pg_proc p
    join pg_namespace n on p.pronamespace = n.oid
    where n.nspname = 'public'
      and p.proname  = 'set_app_tenant'
      and p.prosecdef = true
  ) then
    raise exception 'set_app_tenant function missing or not security_definer';
  end if;
end $$;

rollback;
