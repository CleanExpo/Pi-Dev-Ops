-- RA-7119 — standalone durable lesson store migration
--
-- This forward-only migration deliberately has no dependency on migration.sql.
-- It can create the RA-7111 store in an otherwise empty Supabase database, or
-- reconcile the exact table formerly bundled in migration.sql. A plain PostgreSQL
-- fixture must first provide Supabase's service_role.
-- Existing rows are never deleted or rewritten.
BEGIN;

-- Runtime lesson appends are written through to this table and hydrated on boot.
-- The tracked seed is never inserted here. `hash` is the SHA-256 of the raw JSONL
-- line, so retrying an application write upserts onto the same row.
CREATE TABLE IF NOT EXISTS lessons_durable (
  hash       TEXT         PRIMARY KEY,
  line       JSONB        NOT NULL,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lessons_durable_created_at_idx
  ON lessons_durable (created_at);

ALTER TABLE lessons_durable ENABLE ROW LEVEL SECURITY;

-- Replace inside the transaction so repeated application is safe and there is no
-- committed interval where RLS is enabled without the service-role policy.
DROP POLICY IF EXISTS "service_only" ON lessons_durable;
CREATE POLICY "service_only" ON lessons_durable
  FOR ALL TO service_role USING (true);

SELECT 'lessons_durable migration complete' AS status;
COMMIT;
