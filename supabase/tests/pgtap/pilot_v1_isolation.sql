-- supabase/tests/pgtap/pilot_v1_isolation.sql
-- Per ADR 002: assert RLS + tenant isolation on every pilot_* table.
-- Direct remediation for [[portfolio-health-snapshot-2026-05-14]] Margot pattern.
-- Run via GitHub Action (pgtap-pilot.yml) on every PR touching swarm/pilot/** or migrations/**.

begin;
select plan(8);

-- 1. RLS enabled on pilot_suggestions
select ok(
  (select c.relrowsecurity
   from pg_class c join pg_namespace n on c.relnamespace = n.oid
   where n.nspname = 'public' and c.relname = 'pilot_suggestions'),
  'RLS enabled on pilot_suggestions');

-- 2. RLS enabled on pilot_preferences
select ok(
  (select c.relrowsecurity
   from pg_class c join pg_namespace n on c.relnamespace = n.oid
   where n.nspname = 'public' and c.relname = 'pilot_preferences'),
  'RLS enabled on pilot_preferences');

-- 3. RLS enabled on pilot_suggestion_messages
select ok(
  (select c.relrowsecurity
   from pg_class c join pg_namespace n on c.relnamespace = n.oid
   where n.nspname = 'public' and c.relname = 'pilot_suggestion_messages'),
  'RLS enabled on pilot_suggestion_messages');

-- 4. tenant_isolation policy exists on pilot_suggestions
select ok(
  exists(select 1 from pg_policies
         where schemaname = 'public'
           and tablename  = 'pilot_suggestions'
           and policyname = 'tenant_isolation_pilot_suggestions'),
  'tenant_isolation policy present on pilot_suggestions');

-- 5. tenant_isolation policy exists on pilot_preferences
select ok(
  exists(select 1 from pg_policies
         where schemaname = 'public'
           and tablename  = 'pilot_preferences'
           and policyname = 'tenant_isolation_pilot_preferences'),
  'tenant_isolation policy present on pilot_preferences');

-- 6. tenant_isolation policy exists on pilot_suggestion_messages
select ok(
  exists(select 1 from pg_policies
         where schemaname = 'public'
           and tablename  = 'pilot_suggestion_messages'
           and policyname = 'tenant_isolation_pilot_suggestion_messages'),
  'tenant_isolation policy present on pilot_suggestion_messages');

-- 7. pilot_suggestions.pillar is text[] (array type)
select ok(
  (select a.attndims > 0 or t.typcategory = 'A'
   from pg_attribute a
   join pg_class c on a.attrelid = c.oid
   join pg_namespace n on c.relnamespace = n.oid
   join pg_type t on a.atttypid = t.oid
   where n.nspname = 'public'
     and c.relname  = 'pilot_suggestions'
     and a.attname  = 'pillar'
     and a.attnum   > 0),
  'pilot_suggestions.pillar is an array type (text[])');

-- 8. set_app_tenant function exists and is security definer
select ok(
  exists(
    select 1 from pg_proc p
    join pg_namespace n on p.pronamespace = n.oid
    where n.nspname = 'public'
      and p.proname  = 'set_app_tenant'
      and p.prosecdef = true
  ),
  'set_app_tenant function exists with security_definer=true');

select * from finish();
rollback;
