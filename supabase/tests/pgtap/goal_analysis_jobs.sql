-- supabase/tests/pgtap/goal_analysis_jobs.sql
-- UNI-3306 step 5: the goal_analysis_jobs rules hold in the database itself, not
-- only in the app. Same idiom as pilot_v1_isolation.sql: plain DO blocks that raise.
-- Everything runs in one transaction that is rolled back, so the table is left empty.
-- The simultaneous-submission case needs two sessions: tests/test_goal_analysis_jobs_pg.py.

begin;

-- A helper scoped to this transaction: run one statement, require the given SQLSTATE.
create function pg_temp.expect_error(stmt text, want text, label text) returns void
language plpgsql as $$
begin
  execute stmt;
  raise exception 'expected % (%) but the statement succeeded: %', want, label, stmt;
exception
  when others then
    if sqlstate <> want then
      raise exception 'expected % (%) but got % %: %', want, label, sqlstate, sqlerrm, stmt;
    end if;
end;
$$;

do $$
declare
  h1 constant text := repeat('a', 64);
  h2 constant text := repeat('b', 64);
  n int;
  jid uuid;
begin
  -- 1. RLS on, and the only policy is service_role.
  if not coalesce((select c.relrowsecurity from pg_class c
                   join pg_namespace s on s.oid = c.relnamespace
                   where s.nspname = 'public' and c.relname = 'goal_analysis_jobs'), false) then
    raise exception 'goal_analysis_jobs is missing or RLS is not enabled on it';
  end if;
  if (select array_agg(p.policyname || ':' || array_to_string(p.roles, ','))
      from pg_policies p where p.schemaname = 'public' and p.tablename = 'goal_analysis_jobs')
     is distinct from array['service_only:service_role'] then
    raise exception 'goal_analysis_jobs policies are not exactly service_only for service_role';
  end if;

  -- 2. A valid queued job is accepted with the documented defaults.
  insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
  values ('p1', 'Finalise Stage 1', 'Tickets written', h1, 'key-0001') returning id into jid;
  select count(*) into n from goal_analysis_jobs
   where id = jid and status = 'queued' and attempt = 0 and retry_count = 0
     and evidence_links = '[]'::jsonb and ended_at is null;
  if n <> 1 then raise exception 'queued job defaults are wrong'; end if;
end $$;

-- 3. One active job per goal per project (Q6).
select pg_temp.expect_error(
  $q$insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
     values ('p1', 'Finalise Stage 1', 'Tickets written', repeat('a', 64), 'key-0002')$q$,
  '23505', 'second active job for the same goal and project');

-- The same goal in another project, or another goal in the same project, is allowed.
insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
values ('p2', 'Finalise Stage 1', 'Tickets written', repeat('a', 64), 'key-0003'),
       ('p1', 'Another goal', 'Done', repeat('b', 64), 'key-0004');

-- 4. One-time key is unique across the table, whatever the content.
select pg_temp.expect_error(
  $q$insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
     values ('p9', 'Different', 'Different', repeat('c', 64), 'key-0001')$q$,
  '23505', 'reused one-time key');

-- 5. Fencing: a claim moves attempt n to n+1 only when the row still holds n.
do $$
declare n int;
begin
  update goal_analysis_jobs
     set status = 'running', attempt = attempt + 1, claimed_by = 'server-a',
         claim_expires_at = now() + interval '60 seconds',
         attempt_deadline = now() + interval '5 minutes',
         started_at = now(), last_progress_at = now()
   where idempotency_key = 'key-0001' and attempt = 0;
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'first claim changed % rows, expected 1', n; end if;

  -- A late writer still holding attempt 0 changes nothing.
  update goal_analysis_jobs set status = 'finished', result = '{}'::jsonb, ended_at = now()
   where idempotency_key = 'key-0001' and attempt = 0;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'stale attempt wrote % rows, expected 0', n; end if;
end $$;

-- A running job still blocks a resubmission of the same goal.
select pg_temp.expect_error(
  $q$insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
     values ('p1', 'Finalise Stage 1', 'Tickets written', repeat('a', 64), 'key-0005')$q$,
  '23505', 'resubmission while running');

-- 6. Interrupted with its retry left is still active; after the retry is used it is not.
update goal_analysis_jobs set status = 'interrupted' where idempotency_key = 'key-0001';
select pg_temp.expect_error(
  $q$insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
     values ('p1', 'Finalise Stage 1', 'Tickets written', repeat('a', 64), 'key-0006')$q$,
  '23505', 'resubmission while interrupted with a retry left');

-- 7. One retry at most: retry_count cannot exceed 1.
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set retry_count = 2 where idempotency_key = 'key-0001'$q$,
  '23514', 'second retry');

-- 8. Status invariants.
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set status = 'running', claimed_by = null
      where idempotency_key = 'key-0004'$q$,
  '23514', 'running without a claim');
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set status = 'finished', ended_at = now()
      where idempotency_key = 'key-0004'$q$,
  '23514', 'finished without a result');
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set status = 'failed', ended_at = now()
      where idempotency_key = 'key-0004'$q$,
  '23514', 'failed without a reason');
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set status = 'failed', failure_reason = 'x'
      where idempotency_key = 'key-0004'$q$,
  '23514', 'final status without ended_at');
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set ended_at = now() where idempotency_key = 'key-0004'$q$,
  '23514', 'ended_at on an unfinished job');
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set status = 'paused' where idempotency_key = 'key-0004'$q$,
  '23514', 'unknown status');
select pg_temp.expect_error(
  $q$insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
     values ('p1', 'g', 'a', 'NOT-A-HASH', 'key-0007')$q$,
  '23514', 'malformed goal hash');
select pg_temp.expect_error(
  $q$update goal_analysis_jobs set evidence_links = '{}'::jsonb where idempotency_key = 'key-0004'$q$,
  '23514', 'evidence_links not an array');

-- 9. A finished job frees the goal for a new submission.
do $$
begin
  update goal_analysis_jobs
     set status = 'failed', failure_reason = 'retry used', retry_count = 1, ended_at = now()
   where idempotency_key = 'key-0001';
  insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)
  values ('p1', 'Finalise Stage 1', 'Tickets written', repeat('a', 64), 'key-0008');
end $$;

-- 10. Roles other than service_role see no rows even when granted SELECT.
grant select on goal_analysis_jobs to anon, authenticated;
set local role authenticated;
do $$
begin
  if (select count(*) from goal_analysis_jobs) <> 0 then
    raise exception 'authenticated can read goal_analysis_jobs rows';
  end if;
end $$;
reset role;
set local role anon;
do $$
begin
  if (select count(*) from goal_analysis_jobs) <> 0 then
    raise exception 'anon can read goal_analysis_jobs rows';
  end if;
end $$;
reset role;

select 'goal_analysis_jobs assertions passed' as status;
rollback;
