-- Control Goal project briefs. Service role only.
-- Independent of intake_projects (CIP partner workspace).
BEGIN;

CREATE TABLE IF NOT EXISTS goal_projects (
  id           TEXT         PRIMARY KEY,
  title        TEXT         NOT NULL,
  description  TEXT         NOT NULL,
  audience     TEXT         NOT NULL,
  problem      TEXT         NOT NULL DEFAULT '',
  users        TEXT         NOT NULL DEFAULT '',
  outcomes     TEXT         NOT NULL DEFAULT '',
  constraints  TEXT         NOT NULL DEFAULT '',
  out_of_scope TEXT         NOT NULL DEFAULT '',
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS goal_projects_created_at_idx
  ON goal_projects (created_at DESC);

ALTER TABLE goal_projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_only" ON goal_projects;
CREATE POLICY "service_only" ON goal_projects
  FOR ALL TO service_role USING (true);

SELECT 'goal_projects migration complete' AS status;
COMMIT;
