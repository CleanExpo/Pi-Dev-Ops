-- conversation_digests — the shared conversation brain (Milestone 3).
--
-- Three machines run Claude Code; each one's transcripts live only in that
-- machine's ~/.claude/projects/**/*.jsonl. Both existing readers of that lake
-- are machine-local dead ends: app/server/pi_ceo_session_fts.py indexes into a
-- SQLite FTS5 file under ~/.claude, and scripts/sync_claude_sessions.py writes
-- redacted digests into a local Obsidian vault. Neither is reachable from
-- another machine, so no machine can search what the others did.
--
-- This table is the shared half. RAW JSONL NEVER TRAVELS — only the redacted
-- digest a client already produced, and the server redacts a second time
-- (app/server/routes/conversations.py) before any row reaches here.
--
-- `id` is "<machine>:<session_id>" so a re-sync of the same session upserts
-- onto its own row instead of accumulating duplicates, and the same session id
-- observed on two machines stays two rows rather than silently overwriting.
--
-- Idempotent; safe to re-run. Forward-only: no existing row is deleted or
-- rewritten.
BEGIN;

CREATE TABLE IF NOT EXISTS conversation_digests (
  id               TEXT        PRIMARY KEY,
  machine          TEXT        NOT NULL,
  project_dir      TEXT,
  title            TEXT,
  digest_md        TEXT,
  turn_count       INTEGER,
  started_at       TIMESTAMPTZ,
  last_activity_at TIMESTAMPTZ,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Search vector. GENERATED ... STORED rather than a trigger so it can never
-- drift from the row it describes — a digest updated by an upsert re-derives
-- its vector in the same statement. Added by ALTER rather than inside CREATE
-- TABLE so this migration also reconciles a table that already exists without
-- it (the CREATE above is a no-op in that case and would skip the column).
ALTER TABLE conversation_digests
  ADD COLUMN IF NOT EXISTS search_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(digest_md, ''))
  ) STORED;

-- The search path: PostgREST `search_tsv=fts(english).<query>` is a @@ match,
-- which is a sequential scan without this.
CREATE INDEX IF NOT EXISTS conversation_digests_search_idx
  ON conversation_digests USING GIN (search_tsv);

-- The browse path: "what did <machine> do most recently". Composite in that
-- order because machine is the equality predicate and last_activity_at the
-- ordering, so one index serves both the filtered and (via the leading column
-- being skippable only on a full scan) the per-machine case.
CREATE INDEX IF NOT EXISTS conversation_digests_machine_recent_idx
  ON conversation_digests (machine, last_activity_at DESC);

ALTER TABLE conversation_digests ENABLE ROW LEVEL SECURITY;

-- service_only, matching lessons_durable (supabase/migrations/20260804190000).
-- NOT the public_read/service_write/service_update trio that `sessions` carries:
-- a sessions row is build metadata, while a row here is the redacted content of
-- a private conversation, and public_read would hand every one of them to any
-- holder of the browser-public anon key. Same reasoning as the mesh_* tables,
-- which are likewise service-role only — this server is the sole reader and
-- writer, and machines authenticate to IT with X-Pi-CEO-Secret rather than ever
-- holding the service-role key.
--
-- Replaced inside the transaction so repeated application is safe and there is
-- no committed interval where RLS is on without the service-role policy.
DROP POLICY IF EXISTS "service_only" ON conversation_digests;
CREATE POLICY "service_only" ON conversation_digests
  FOR ALL TO service_role USING (true);

SELECT 'conversation_digests migration complete' AS status;
COMMIT;
