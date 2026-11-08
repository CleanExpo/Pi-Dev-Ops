-- Goal analysis job clean-up on the database clock (UNI-3306 PR 3, grill 14 Q7).
-- Service role only. One function: delete finished and failed jobs 90 days after
-- ended_at. Active jobs (queued, running, interrupted) are never touched by it.
-- Decisions:
--   * Same clock rule as 20261108T010000: the cutoff is goal_job_now() minus 90 days.
--     No worker time and no other clock appear here (the test in
--     tests/test_goal_analysis_jobs_pg_lock.py holds this file to it too).
--   * Why reading the clock before selecting rows is safe here: ended_at is written
--     once, by finish/fail/recover, and those functions only act on running rows, so a
--     finished or failed row is never updated again. A cutoff read a moment early can
--     only keep a row one run longer; it can never delete a row that is still live.
--   * Bounded: p_limit rows per call, oldest first, so one call holds a small number of
--     row locks. The caller repeats until fewer than p_limit ids come back.
--     p_limit outside 1..1000 is an error, never a silent no-op.
--   * FOR UPDATE SKIP LOCKED: a row some other session holds is left for the next run.
--   * The status test is kept even though the table constraint
--     goal_analysis_jobs_ended_iff_final already stops an active row having ended_at:
--     the function must not rely on a constraint to protect running work.
--   * Returns the ids it deleted, so a caller counts rows it can see. An error is an
--     error (HTTP 4xx/5xx through PostgREST); it can never look like "deleted 0".
--   * SECURITY INVOKER, EXECUTE revoked from PUBLIC, anon and authenticated, granted to
--     service_role, like the other goal_job_* functions.
--
-- Applied to the live database only after the PR merges, after 20261108T010000.
-- Rollback: nothing else references it.
--   DROP FUNCTION IF EXISTS goal_job_purge_ended(integer);
BEGIN;

CREATE OR REPLACE FUNCTION goal_job_purge_ended(p_limit integer)
RETURNS TABLE (id uuid)
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_at timestamptz;
BEGIN
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 1000 THEN
    RAISE EXCEPTION 'goal_job_purge_ended: p_limit must be between 1 and 1000'
      USING ERRCODE = '22023';
  END IF;
  v_at := goal_job_now();
  RETURN QUERY
  WITH doomed AS (
    SELECT j.id
      FROM goal_analysis_jobs AS j
     WHERE j.status IN ('finished', 'failed')
       AND j.ended_at < v_at - interval '90 days'
     ORDER BY j.ended_at
     LIMIT p_limit
       FOR UPDATE SKIP LOCKED)
  DELETE FROM goal_analysis_jobs AS d
   USING doomed
   WHERE d.id = doomed.id
  RETURNING d.id;
END
$$;

REVOKE ALL ON FUNCTION goal_job_purge_ended(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION goal_job_purge_ended(integer) TO service_role;

SELECT 'goal_analysis_job_purge migration complete' AS status;
COMMIT;
