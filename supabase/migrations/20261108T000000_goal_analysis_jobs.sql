-- Goal analysis jobs (UNI-3306, card M-PDO-GOAL-ANALYZE-ASYNC). Service role only.
-- One record per submit-then-check analysis: the input, its status, the claim that
-- fences which server may write, and the finished result. Decisions: grill
-- 14-pdo-goal-analyze-async, Q1 (one table, five statuses, result in the record),
-- Q2 (attempt-number fencing, one retry at most), Q3 (claim expiry and attempt
-- deadline on the record), Q6 (one active job per goal per project, enforced here),
-- Q7 (finished and failed jobs removed 90 days after ended_at, by the app).
--
-- Applied to the live database only after the PR merges; the analysis path stays
-- behind GOAL_ANALYZE_ASYNC=0 until the table is confirmed present (Q8).
-- Rollback: the table is new and nothing references it.
--   DROP TABLE IF EXISTS goal_analysis_jobs;
BEGIN;

CREATE TABLE IF NOT EXISTS goal_analysis_jobs (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       TEXT         NOT NULL CHECK (project_id <> ''),
  goal             TEXT         NOT NULL CHECK (length(goal) BETWEEN 1 AND 20000),
  acceptance       TEXT         NOT NULL CHECK (length(acceptance) BETWEEN 1 AND 20000),
  -- SHA-256 (lowercase hex) of the normalised goal and acceptance, so the
  -- one-active-job rule indexes a fixed-size key, not free text.
  goal_sha256      TEXT         NOT NULL CHECK (goal_sha256 ~ '^[0-9a-f]{64}$'),
  -- One-time key from the submitting browser; the same key returns the same job.
  idempotency_key  TEXT         NOT NULL UNIQUE
                                CHECK (length(idempotency_key) BETWEEN 8 AND 200),
  status           TEXT         NOT NULL DEFAULT 'queued'
                                CHECK (status IN ('queued', 'running', 'finished',
                                                  'failed', 'interrupted')),
  -- Fencing: every claim sets attempt to the next number, and every later write
  -- filters on attempt = the claimer's number and must change exactly one row.
  attempt          INTEGER      NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  -- Raised in the same update as a re-claim of an interrupted job. One retry at
  -- most across all servers: a value above 1 cannot be stored.
  retry_count      INTEGER      NOT NULL DEFAULT 0 CHECK (retry_count BETWEEN 0 AND 1),
  claimed_by       TEXT,
  claim_expires_at TIMESTAMPTZ,
  attempt_deadline TIMESTAMPTZ,
  result           JSONB,
  evidence_links   JSONB        NOT NULL DEFAULT '[]'::jsonb
                                CHECK (jsonb_typeof(evidence_links) = 'array'),
  failure_reason   TEXT,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
  started_at       TIMESTAMPTZ,
  last_progress_at TIMESTAMPTZ,
  ended_at         TIMESTAMPTZ,
  CONSTRAINT goal_analysis_jobs_running_is_claimed CHECK (
    status <> 'running'
    OR (attempt >= 1 AND claimed_by IS NOT NULL AND claimed_by <> ''
        AND claim_expires_at IS NOT NULL AND attempt_deadline IS NOT NULL)
  ),
  CONSTRAINT goal_analysis_jobs_finished_has_result CHECK (
    status <> 'finished' OR result IS NOT NULL
  ),
  CONSTRAINT goal_analysis_jobs_failed_has_reason CHECK (
    status <> 'failed' OR (failure_reason IS NOT NULL AND failure_reason <> '')
  ),
  CONSTRAINT goal_analysis_jobs_ended_iff_final CHECK (
    (status IN ('finished', 'failed')) = (ended_at IS NOT NULL)
  )
);

-- Q6: one active job per goal per project. Active includes an interrupted job
-- that still has its retry, so a resubmission in the retry window cannot start
-- a second analysis. A second insert loses with unique_violation (HTTP 409).
CREATE UNIQUE INDEX IF NOT EXISTS goal_analysis_jobs_one_active_idx
  ON goal_analysis_jobs (project_id, goal_sha256)
  WHERE status IN ('queued', 'running')
     OR (status = 'interrupted' AND retry_count < 1);

-- Startup recovery and takeover scan the unfinished jobs by claim expiry.
CREATE INDEX IF NOT EXISTS goal_analysis_jobs_unfinished_idx
  ON goal_analysis_jobs (claim_expires_at)
  WHERE status IN ('queued', 'running', 'interrupted');

-- Q7 daily clean-up scans ended jobs by age.
CREATE INDEX IF NOT EXISTS goal_analysis_jobs_ended_at_idx
  ON goal_analysis_jobs (ended_at)
  WHERE ended_at IS NOT NULL;

ALTER TABLE goal_analysis_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_only" ON goal_analysis_jobs;
CREATE POLICY "service_only" ON goal_analysis_jobs
  FOR ALL TO service_role USING (true);

SELECT 'goal_analysis_jobs migration complete' AS status;
COMMIT;
