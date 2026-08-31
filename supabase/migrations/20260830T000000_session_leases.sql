-- Session ownership leases — one machine per interrupted session.
--
-- Before this, three replicas booting all called fetch_interrupted_sessions()
-- and each resumed the SAME rows: `sessions` carried no ownership column at
-- all, unlike mesh_work_claims whose `mesh_work_claims_one_open` partial unique
-- index makes a fleet-wide double-claim impossible. claimed_by +
-- lease_expires_at turn recovery into a conditional PATCH
-- (app/server/supabase_log.py::claim_interrupted_session) that exactly one
-- caller can win: the filter demands the lease is unowned OR already expired,
-- and PostgREST returns the updated rows, so "won" is "exactly one row back".
--
-- The lease EXPIRES rather than being released, because the failure being
-- recovered from is a machine that died — a dead owner can never release. Every
-- checkpoint write renews it, so a live resume keeps the row and a crashed one
-- hands it back after lease_minutes.
--
-- Idempotent; safe to re-run. RLS is already enabled on `sessions` with
-- public_read / service_write / service_update (supabase/migration.sql:73-79) —
-- these columns inherit those policies, so no policy change belongs here.
BEGIN;

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS claimed_by       TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

-- Matches the claim filter's leading predicates (status, then lease expiry).
-- sessions_status_idx already exists but stops at status; interrupted rows are
-- the ones scanned on every replica boot, which is exactly when the database is
-- busiest with N replicas asking the same question at once.
CREATE INDEX IF NOT EXISTS sessions_lease_idx
  ON sessions (status, lease_expires_at);

SELECT 'session_leases migration complete' AS status;
COMMIT;
