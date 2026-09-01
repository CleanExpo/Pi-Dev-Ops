-- supabase/tests/pgtap/rls_coverage.sql
-- Every table in `public` must have RLS enabled AND at least one policy.
--
-- Its sibling `pilot_v1_isolation.sql` names three pilot_* tables one at a time.
-- That shape only ever covers tables somebody remembered to add, which is how
-- four tables reached main with no RLS at all: the job that should have caught
-- them applied `supabase/migrations/*pilot*.sql` — one file of seventeen — so it
-- never read the migration that created them. This file asserts over the
-- CATALOG instead, so a new table is covered by existing, not by being listed.
--
-- Same idiom as that sibling: plain `do $$ ... raise exception`, not literal
-- pgtap, despite the directory name.
--
-- TWO FAILURE MODES, both real:
--   * RLS off            — the table is readable by anyone the grants admit.
--   * RLS on, no policy  — RLS denies by default, so the table is readable by
--                          NOBODY. Silently broken rather than silently open,
--                          and equally unintended. `continuation_horizons` is
--                          in exactly this state today.
--
-- THE BASELINE IS SHRINK-ONLY. A listed table that now passes fails this file
-- with "remove it from the baseline" — the same ratchet as
-- .github/scripts/file_length_lint.py, and the reason the list cannot quietly
-- become permanent. Entries are what is TRUE today, not what is acceptable.
--
-- WHAT THIS FILE DOES NOT PROVE, since it has already been misread once.
-- It runs against a shadow database built from THIS REPO'S FILES. It therefore
-- asserts that the declared schema is sound — never that the live database is.
-- The two differ:
--   * RA-7393 read the five entries above as a live exposure. They are not:
--     measured 2026-08-31, none of those five tables exists in any live project.
--     They are true statements about migrations, and only that.
--   * Conversely, 20 of Pi CEO's 57 live tables were declared nowhere in this
--     repo and so were invisible here — a third of production, on a gate whose
--     name suggests otherwise. The 2026-09-01 back-fill and the mesh/schema
--     apply step close today's gap; nothing stops it reopening the next time a
--     table is created straight against production.
-- Measuring the live catalog needs credentials CI does not hold. It is a
-- different job, and it does not exist yet (RA-7396).

begin;

create temporary table _rls_baseline (tbl text primary key, why text) on commit drop;

-- Measured from pg_class on a shadow database with every migration applied,
-- NOT grepped from the migration files: `llm_costs` and `margot_conversations`
-- look RLS-less in `supabase/migrations/` and are in fact covered by
-- `supabase/migration.sql`. Counting the shape of a thing is not measuring it.
insert into _rls_baseline (tbl, why) values
  ('youtube_signal_items',      'RLS off — 20260820032000_youtube_intent_catalog.sql'),
  ('youtube_topics',            'RLS off — 20260820032000_youtube_intent_catalog.sql'),
  ('persona_traits',            'RLS off — 20260820032000_youtube_intent_catalog.sql'),
  ('vertical_pathway_signals',  'RLS off — 20260820032000_youtube_intent_catalog.sql'),
  ('continuation_horizons',     'RLS on but zero policies — 20260827_continuation_horizons.sql'),
  -- Added 2026-09-01 with 20260901T000000_backfill_live_tables.sql. These four
  -- are live in Pi CEO and were declared nowhere, so this gate had never seen
  -- them; declaring them is what brings them under it. They carry RLS and NO
  -- policy in production — the state Supabase's advisor reports as
  -- rls_enabled_no_policy — so they enter the baseline in the state they are
  -- actually in. Policies were NOT invented for them: this repo has no consumer
  -- for three of the four, and writing a policy here would change their
  -- semantics for whoever does. All four are empty, so nothing is locked out.
  ('claude_api_costs',          'RLS on, zero policies live — declared by the 2026-09-01 back-fill'),
  ('heartbeat_log',             'RLS on, zero policies live — declared by the 2026-09-01 back-fill'),
  ('triage_log',                'RLS on, zero policies live — declared by the 2026-09-01 back-fill'),
  ('workflow_runs',             'RLS on, zero policies live — declared by the 2026-09-01 back-fill');

do $$
declare
  offenders text;
  stale     text;
begin
  -- 1. RLS disabled, and not baselined.
  select string_agg(c.relname, ', ' order by c.relname) into offenders
  from pg_class c
  join pg_namespace n on c.relnamespace = n.oid
  where n.nspname = 'public'
    and c.relkind = 'r'
    and not c.relrowsecurity
    and c.relname not in (select tbl from _rls_baseline);
  if offenders is not null then
    raise exception
      'RLS not enabled on: %. Add `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;` and a policy '
      'in the migration that creates the table.', offenders;
  end if;

  -- 2. RLS enabled but no policy — denies everyone, including the service role.
  select string_agg(c.relname, ', ' order by c.relname) into offenders
  from pg_class c
  join pg_namespace n on c.relnamespace = n.oid
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relrowsecurity
    and c.relname not in (select tbl from _rls_baseline)
    and not exists (
      select 1 from pg_policies p
      where p.schemaname = 'public' and p.tablename = c.relname
    );
  if offenders is not null then
    raise exception
      'RLS enabled but NO policy on: %. With RLS on and no policy the table is '
      'readable by nobody. Add a policy, or do not enable RLS.', offenders;
  end if;

  -- 3. Ratchet: a baselined table that now passes must leave the baseline.
  select string_agg(b.tbl, ', ' order by b.tbl) into stale
  from _rls_baseline b
  join pg_class c on c.relname = b.tbl
  join pg_namespace n on c.relnamespace = n.oid and n.nspname = 'public'
  where c.relkind = 'r'
    and c.relrowsecurity
    and exists (
      select 1 from pg_policies p
      where p.schemaname = 'public' and p.tablename = c.relname
    );
  if stale is not null then
    raise exception
      'These are now covered and must be REMOVED from the baseline in %: %. '
      'The baseline only ever shrinks.', 'supabase/tests/pgtap/rls_coverage.sql', stale;
  end if;

  -- 4. Ratchet: a baselined table that no longer exists is dead weight.
  select string_agg(b.tbl, ', ' order by b.tbl) into stale
  from _rls_baseline b
  where not exists (
    select 1 from pg_class c
    join pg_namespace n on c.relnamespace = n.oid
    where n.nspname = 'public' and c.relkind = 'r' and c.relname = b.tbl
  );
  if stale is not null then
    raise exception
      'Baselined tables that no longer exist: %. Remove them from the baseline.', stale;
  end if;

  raise notice 'rls_coverage: every public table has RLS and a policy (% baselined)',
    (select count(*) from _rls_baseline);
end $$;

commit;
