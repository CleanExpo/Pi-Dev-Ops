-- Goal analysis job writes on the database clock (UNI-3306, card M-PDO-GOAL-ANALYZE-ASYNC).
-- Service role only. Seven functions, created together in one transaction.
-- Every time-dependent write to goal_analysis_jobs (claim, heartbeat, finish, fail,
-- recovery) is one UPDATE inside one of these functions, so every ownership decision
-- and every expiry value uses the database clock. Decisions:
--   * Review rounds 1-4 kept finding one defect kind: a worker write's ownership test
--     used a time taken on the worker, which could be stale by the time the database
--     applied the write (a finish stamped T0+59 and applied T0+62, after the claim
--     lapsed, still won). A PostgREST filter cannot reference now(), so the test moves
--     here. No Python code computes a time used in an ownership decision or an expiry.
--   * now() is the transaction start. A PostgREST RPC is one statement in its own
--     transaction, so now() is the moment the database received the call.
--   * ONE owner of "this attempt still owns the row": goal_job_is_live(). Heartbeat,
--     finish and fail call it; nothing re-states it. Recovery is its complement, with
--     the 5 s recovery margin.
--   * Constants live here: claim 60 s, attempt deadline 300 s, recovery margin 5 s.
--   * Each write is ONE UPDATE ... RETURNING. There is no read-then-write window; a
--     concurrent write waits on the row lock and then re-checks its WHERE clause.
--   * SECURITY INVOKER: the caller's (service_role's) table rights and row policy
--     apply. EXECUTE is revoked from PUBLIC, anon and authenticated, because Supabase's
--     default privileges grant new functions in public to anon and authenticated.
--
-- Applied to the live database only after the PR merges, after 20261108T000000.
-- Rollback: nothing else references these functions.
--   DROP FUNCTION IF EXISTS goal_job_recover();
--   DROP FUNCTION IF EXISTS goal_job_fail(uuid, integer, text);
--   DROP FUNCTION IF EXISTS goal_job_finish(uuid, integer, jsonb, jsonb);
--   DROP FUNCTION IF EXISTS goal_job_heartbeat(uuid, integer, text);
--   DROP FUNCTION IF EXISTS goal_job_claim(uuid, text);
--   DROP FUNCTION IF EXISTS goal_job_retry_unused(goal_analysis_jobs);
--   DROP FUNCTION IF EXISTS goal_job_is_live(goal_analysis_jobs, integer);
BEGIN;

-- The one owner of ownership: running, this attempt, claim unexpired, deadline ahead.
CREATE OR REPLACE FUNCTION goal_job_is_live(j goal_analysis_jobs, p_attempt integer)
RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  SELECT j.status = 'running'
     AND j.attempt = p_attempt
     AND j.claim_expires_at > now()
     AND j.attempt_deadline > now()
$$;

-- The one owner of "the single retry is still unused": claim and recovery call it.
CREATE OR REPLACE FUNCTION goal_job_retry_unused(j goal_analysis_jobs)
RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  SELECT j.retry_count < 1
$$;

-- Take a queued job, or an interrupted one whose single retry is unused.
CREATE OR REPLACE FUNCTION goal_job_claim(p_id uuid, p_server text)
RETURNS SETOF goal_analysis_jobs
LANGUAGE sql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  UPDATE goal_analysis_jobs AS j
     SET status           = 'running',
         attempt          = j.attempt + 1,
         retry_count      = CASE WHEN j.status = 'interrupted' THEN 1 ELSE j.retry_count END,
         claimed_by       = p_server,
         claim_expires_at = now() + interval '60 seconds',
         attempt_deadline = now() + interval '300 seconds',
         started_at       = coalesce(j.started_at, now()),
         last_progress_at = now()
   WHERE j.id = p_id
     AND (j.status = 'queued' OR (j.status = 'interrupted' AND goal_job_retry_unused(j)))
  RETURNING j.*
$$;

CREATE OR REPLACE FUNCTION goal_job_heartbeat(p_id uuid, p_attempt integer, p_server text)
RETURNS SETOF goal_analysis_jobs
LANGUAGE sql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  UPDATE goal_analysis_jobs AS j
     SET claim_expires_at = now() + interval '60 seconds',
         last_progress_at = now()
   WHERE j.id = p_id AND goal_job_is_live(j, p_attempt) AND j.claimed_by = p_server
  RETURNING j.*
$$;

CREATE OR REPLACE FUNCTION goal_job_finish(p_id uuid, p_attempt integer, p_result jsonb, p_links jsonb)
RETURNS SETOF goal_analysis_jobs
LANGUAGE sql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  UPDATE goal_analysis_jobs AS j
     SET status = 'finished', result = p_result, evidence_links = p_links,
         ended_at = now(), claim_expires_at = NULL
   WHERE j.id = p_id AND goal_job_is_live(j, p_attempt)
  RETURNING j.*
$$;

CREATE OR REPLACE FUNCTION goal_job_fail(p_id uuid, p_attempt integer, p_reason text)
RETURNS SETOF goal_analysis_jobs
LANGUAGE sql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  UPDATE goal_analysis_jobs AS j
     SET status = 'failed', failure_reason = p_reason,
         ended_at = now(), claim_expires_at = NULL
   WHERE j.id = p_id AND goal_job_is_live(j, p_attempt)
  RETURNING j.*
$$;

-- Running jobs whose claim lapsed or deadline passed more than 5 s ago: interrupted
-- while the single retry is unused, otherwise failed. One statement, all rows.
CREATE OR REPLACE FUNCTION goal_job_recover()
RETURNS SETOF goal_analysis_jobs
LANGUAGE sql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  UPDATE goal_analysis_jobs AS j
     SET status           = CASE WHEN goal_job_retry_unused(j) THEN 'interrupted' ELSE 'failed' END,
         claimed_by       = CASE WHEN goal_job_retry_unused(j) THEN NULL ELSE j.claimed_by END,
         failure_reason   = CASE WHEN goal_job_retry_unused(j) THEN j.failure_reason
                                 ELSE 'interrupted after its one retry' END,
         ended_at         = CASE WHEN goal_job_retry_unused(j) THEN NULL ELSE now() END,
         claim_expires_at = NULL
   WHERE j.status = 'running'
     AND (j.claim_expires_at < now() - interval '5 seconds'
          OR j.attempt_deadline < now() - interval '5 seconds')
  RETURNING j.*
$$;

REVOKE ALL ON FUNCTION goal_job_is_live(goal_analysis_jobs, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_retry_unused(goal_analysis_jobs) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_claim(uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_heartbeat(uuid, integer, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_finish(uuid, integer, jsonb, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_fail(uuid, integer, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_recover() FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION goal_job_is_live(goal_analysis_jobs, integer) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_retry_unused(goal_analysis_jobs) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_claim(uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_heartbeat(uuid, integer, text) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_finish(uuid, integer, jsonb, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_fail(uuid, integer, text) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_recover() TO service_role;

SELECT 'goal_analysis_job_functions migration complete' AS status;
COMMIT;
