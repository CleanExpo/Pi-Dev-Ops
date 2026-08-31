-- project_requirements + wiki_source_staging — the knowledge front door (M4).
--
-- Two tables, two distinct gaps in the wiki pipeline.
--
-- 1. `project_requirements` — the registry the Librarian scores relevance
--    against. `swarm/wiki_ingest._identify_targets()` currently chooses its ≤5
--    target pages from `index.md` alone, so it knows what the wiki ALREADY
--    contains and nothing about what the projects actually need. That makes
--    "is this source relevant?" unanswerable: every source looks equally
--    on-topic to a chooser with no statement of intent to compare against.
--
-- 2. `wiki_source_staging` — the drop zone the cloud can reach.
--    `swarm/sources_watcher.py` ingests `Sources/*.md`, which is a folder on
--    the brain host. `docs/briefs/estate-librarian-v1.md` §3 marks exactly that
--    as UNREACHABLE_FROM_NODE: a Railway container, a phone, or another machine
--    has no way to put a document into the pipeline. Rows land here; the brain
--    host drains them to `Sources/` on its own cycle.
--
-- UPLOADED CONTENT IS HOSTILE DATA (estate-librarian §4). A staging row is inert
-- text plus a status, never an instruction. `filename` is validated against
-- `swarm.ingest_guard.SAFE_NAME` BEFORE insert, so a row can never name a path
-- outside the Sources/ directory, and the drain re-validates rather than
-- trusting what it reads back.
--
-- NO CHECK CONSTRAINT ON `status`, deliberately. `sessions` carried
-- `sessions_status_check` accepting only running/done/error; the build
-- lifecycle then grew to nine states and RA-1407 had to DROP the constraint in
-- a migration (supabase/migration.sql:66). The same shape of mistake is
-- available here. `status` is enforced in `app/server/wiki_source_store.py`,
-- the single write path, where widening the set is a code change rather than a
-- migration against a live table.
--
-- Idempotent; safe to re-run. Forward-only: no existing row is deleted.
BEGIN;

-- ── project_requirements ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS project_requirements (
  -- "<project_key>:<slug>" so the same requirement slug can exist for two
  -- projects without collision.
  id            TEXT        PRIMARY KEY,
  -- Routes on config/harness/projects.json `id`, NEVER on `repo`: `id` is
  -- unique across all 12 entries and `repo` is not — CleanExpo/Pi-Dev-Ops
  -- deliberately carries both `pi-dev-ops` and `margot`, so a repo-keyed
  -- lookup silently picks one of them.
  project_key   TEXT        NOT NULL,
  title         TEXT        NOT NULL,
  detail        TEXT,
  -- Scoring hints for the Librarian. Plain text array, not a tsvector: this is
  -- matched against a source's topic by an LLM, not by Postgres full-text.
  keywords      TEXT[]      NOT NULL DEFAULT '{}',
  -- Soft delete. A requirement that is no longer current should stop steering
  -- ingestion without erasing the record of what was once wanted.
  active        BOOLEAN     NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The read the Librarian actually issues: "active requirements for this project".
CREATE INDEX IF NOT EXISTS project_requirements_active_idx
  ON project_requirements (project_key, active);

-- ── wiki_source_staging ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wiki_source_staging (
  -- sha256 of the body. Re-uploading identical content upserts onto its own row
  -- instead of queueing the same document twice — the drain is not idempotent
  -- on its own, so the dedupe has to happen at the door.
  id            TEXT        PRIMARY KEY,
  filename      TEXT        NOT NULL,
  body_md       TEXT        NOT NULL,
  -- Free-text label for who uploaded it (a machine name, "takeout", "phone").
  -- Never used to select a path or a permission — it is a breadcrumb only.
  origin        TEXT,
  -- queued | ingested | quarantined | error. See the note above on why this is
  -- not a CHECK constraint.
  status        TEXT        NOT NULL DEFAULT 'queued',
  status_reason TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The drain's only query: oldest queued rows first.
CREATE INDEX IF NOT EXISTS wiki_source_staging_status_idx
  ON wiki_source_staging (status, created_at);

-- ── RLS ──────────────────────────────────────────────────────────────────────
--
-- service_only, matching conversation_digests and the mesh_* tables. NOT the
-- public_read trio that `sessions` carries: a staging row is the full text of a
-- document someone uploaded, and public_read would hand every one of them to any
-- holder of the browser-public anon key. Nodes authenticate to THIS server with
-- X-Pi-CEO-Secret and never hold the service-role key.
--
-- Policies are replaced inside the transaction so repeated application is safe
-- and there is no committed interval where RLS is on without its policy.

ALTER TABLE project_requirements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only" ON project_requirements;
CREATE POLICY "service_only" ON project_requirements
  FOR ALL TO service_role USING (true);

ALTER TABLE wiki_source_staging ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only" ON wiki_source_staging;
CREATE POLICY "service_only" ON wiki_source_staging
  FOR ALL TO service_role USING (true);

SELECT 'requirements_and_staging migration complete' AS status;
COMMIT;
