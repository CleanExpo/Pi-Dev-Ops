-- Goal analysis job writes on the database clock (UNI-3306, card M-PDO-GOAL-ANALYZE-ASYNC).
-- Service role only. Eight functions, created together in one transaction.
-- Every time-dependent write to goal_analysis_jobs (claim, heartbeat, finish, fail,
-- recovery) happens inside one of these functions, so every ownership decision and
-- every expiry value uses the database clock. Decisions:
--   * Review rounds 1-5 kept finding one defect kind: an ownership test used a time
--     that was not the database's time at the moment of the write. r1-r4: a time taken
--     on the worker. r5: now(), which is the TRANSACTION START, so an UPDATE that waited
--     on a row lock re-checked expiry against a time from before the wait.
--   * The design rule that removes the kind: LOCK FIRST, THEN READ THE CLOCK ONCE.
--     Each write function takes the row lock (SELECT ... FOR UPDATE), only then reads
--     goal_job_now(), and uses that one value for every comparison and every stamp in
--     its UPDATE. The UPDATE cannot wait (the lock is already held), so nothing can
--     happen to the row between the clock read and the write.
--   * ONE owner of the clock: goal_job_now() (clock_timestamp(), the real current time).
--     No other function reads a clock; tests/test_goal_analysis_jobs_pg.py fails if the
--     text of this migration names now(), current_timestamp, transaction_timestamp or
--     statement_timestamp, or calls clock_timestamp() outside goal_job_now().
--   * ONE owner of "this attempt still owns the row at time t": goal_job_is_live(j, n, t).
--     Heartbeat, finish and fail call it. Recovery is its complement, with the 5 s margin.
--     ONE owner of "the single retry is unused": goal_job_retry_unused().
--   * Recovery locks running rows with SKIP LOCKED: a row being renewed or finished right
--     now is left for the next pass instead of being judged on a time from before it.
--   * Constants live here: claim 60 s, attempt deadline 300 s, recovery margin 5 s.
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
--   DROP FUNCTION IF EXISTS goal_job_is_live(goal_analysis_jobs, integer, timestamptz);
--   DROP FUNCTION IF EXISTS goal_job_now();
BEGIN;

-- The one owner of the clock. Call it only while holding the row lock.
CREATE OR REPLACE FUNCTION goal_job_now()
RETURNS timestamptz
LANGUAGE sql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  SELECT clock_timestamp()
$$;

-- The one owner of ownership: running, this attempt, claim unexpired, deadline ahead, at p_at.
CREATE OR REPLACE FUNCTION goal_job_is_live(j goal_analysis_jobs, p_attempt integer, p_at timestamptz)
RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  SELECT j.status = 'running'
     AND j.attempt = p_attempt
     AND j.claim_expires_at > p_at
     AND j.attempt_deadline > p_at
$$;

-- The one owner of "the single retry is still unused": claim and recovery call it.
CREATE OR REPLACE FUNCTION goal_job_retry_unused(j goal_analysis_jobs)
RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
  SELECT j.retry_count < 1
$$;

-- Take a queued job, or an interrupted one whose single retry is unused.
CREATE OR REPLACE FUNCTION goal_job_claim(p_id uuid, p_server text)
RETURNS SETOF goal_analysis_jobs
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_at timestamptz;
BEGIN
  PERFORM 1 FROM goal_analysis_jobs WHERE id = p_id FOR UPDATE;
  v_at := goal_job_now();
  RETURN QUERY
  WITH changed AS (
    UPDATE goal_analysis_jobs AS j
       SET status           = 'running',
           attempt          = j.attempt + 1,
           retry_count      = CASE WHEN j.status = 'interrupted' THEN 1 ELSE j.retry_count END,
           claimed_by       = p_server,
           claim_expires_at = v_at + interval '60 seconds',
           attempt_deadline = v_at + interval '300 seconds',
           started_at       = coalesce(j.started_at, v_at),
           last_progress_at = v_at
     WHERE j.id = p_id
       AND (j.status = 'queued' OR (j.status = 'interrupted' AND goal_job_retry_unused(j)))
    RETURNING j.*)
  SELECT * FROM changed;
END
$$;

CREATE OR REPLACE FUNCTION goal_job_heartbeat(p_id uuid, p_attempt integer, p_server text)
RETURNS SETOF goal_analysis_jobs
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_at timestamptz;
BEGIN
  PERFORM 1 FROM goal_analysis_jobs WHERE id = p_id FOR UPDATE;
  v_at := goal_job_now();
  RETURN QUERY
  WITH changed AS (
    UPDATE goal_analysis_jobs AS j
       SET claim_expires_at = v_at + interval '60 seconds',
           last_progress_at = v_at
     WHERE j.id = p_id AND goal_job_is_live(j, p_attempt, v_at) AND j.claimed_by = p_server
    RETURNING j.*)
  SELECT * FROM changed;
END
$$;

CREATE OR REPLACE FUNCTION goal_job_finish(p_id uuid, p_attempt integer, p_result jsonb, p_links jsonb)
RETURNS SETOF goal_analysis_jobs
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_at timestamptz;
BEGIN
  PERFORM 1 FROM goal_analysis_jobs WHERE id = p_id FOR UPDATE;
  v_at := goal_job_now();
  RETURN QUERY
  WITH changed AS (
    UPDATE goal_analysis_jobs AS j
       SET status = 'finished', result = p_result, evidence_links = p_links,
           ended_at = v_at, claim_expires_at = NULL
     WHERE j.id = p_id AND goal_job_is_live(j, p_attempt, v_at)
    RETURNING j.*)
  SELECT * FROM changed;
END
$$;

CREATE OR REPLACE FUNCTION goal_job_fail(p_id uuid, p_attempt integer, p_reason text)
RETURNS SETOF goal_analysis_jobs
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_at timestamptz;
BEGIN
  PERFORM 1 FROM goal_analysis_jobs WHERE id = p_id FOR UPDATE;
  v_at := goal_job_now();
  RETURN QUERY
  WITH changed AS (
    UPDATE goal_analysis_jobs AS j
       SET status = 'failed', failure_reason = p_reason,
           ended_at = v_at, claim_expires_at = NULL
     WHERE j.id = p_id AND goal_job_is_live(j, p_attempt, v_at)
    RETURNING j.*)
  SELECT * FROM changed;
END
$$;

-- Running jobs whose claim lapsed or deadline passed more than 5 s ago: interrupted
-- while the single retry is unused, otherwise failed. Rows locked by a write in
-- progress are skipped and judged on the next pass.
CREATE OR REPLACE FUNCTION goal_job_recover()
RETURNS SETOF goal_analysis_jobs
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_ids uuid[];
  v_at timestamptz;
BEGIN
  SELECT coalesce(array_agg(id), '{}') INTO v_ids FROM (
    SELECT id FROM goal_analysis_jobs WHERE status = 'running' FOR UPDATE SKIP LOCKED) AS locked;
  v_at := goal_job_now();
  RETURN QUERY
  WITH changed AS (
    UPDATE goal_analysis_jobs AS j
       SET status           = CASE WHEN goal_job_retry_unused(j) THEN 'interrupted' ELSE 'failed' END,
           claimed_by       = CASE WHEN goal_job_retry_unused(j) THEN NULL ELSE j.claimed_by END,
           failure_reason   = CASE WHEN goal_job_retry_unused(j) THEN j.failure_reason
                                   ELSE 'interrupted after its one retry' END,
           ended_at         = CASE WHEN goal_job_retry_unused(j) THEN NULL ELSE v_at END,
           claim_expires_at = NULL
     WHERE j.id = ANY (v_ids)
       AND j.status = 'running'
       AND (j.claim_expires_at < v_at - interval '5 seconds'
            OR j.attempt_deadline < v_at - interval '5 seconds')
    RETURNING j.*)
  SELECT * FROM changed;
END
$$;

REVOKE ALL ON FUNCTION goal_job_now() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_is_live(goal_analysis_jobs, integer, timestamptz) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_retry_unused(goal_analysis_jobs) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_claim(uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_heartbeat(uuid, integer, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_finish(uuid, integer, jsonb, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_fail(uuid, integer, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION goal_job_recover() FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION goal_job_now() TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_is_live(goal_analysis_jobs, integer, timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_retry_unused(goal_analysis_jobs) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_claim(uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_heartbeat(uuid, integer, text) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_finish(uuid, integer, jsonb, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_fail(uuid, integer, text) TO service_role;
GRANT EXECUTE ON FUNCTION goal_job_recover() TO service_role;

SELECT 'goal_analysis_job_functions migration complete' AS status;
COMMIT;
