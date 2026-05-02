-- Pi CEO — Supabase Schema Migration
-- Run this in the Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql

-- ── settings ─────────────────────────────────────────────────────────────────
-- Key/value store for app credentials and config (GitHub token, API keys, etc.)
CREATE TABLE IF NOT EXISTS settings (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  key        TEXT        NOT NULL UNIQUE,
  value      TEXT        NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
-- Service role only — anon cannot read or write secrets
CREATE POLICY "service_only_write" ON settings FOR ALL TO service_role USING (true);

-- Seed default rows so GET /api/settings always returns something
INSERT INTO settings (key, value) VALUES
  ('github_token',       ''),
  ('anthropic_api_key',  ''),
  ('analysis_model',     'claude-sonnet-4-6'),
  ('webhook_secret',     ''),
  ('cron_repos',         '[]'),
  ('vercel_token',       ''),
  ('telegram_bot_token', ''),
  ('telegram_chat_id',   ''),
  ('linear_api_key',     '')
ON CONFLICT (key) DO NOTHING;

-- ── sessions ──────────────────────────────────────────────────────────────────
-- One row per analysis run
CREATE TABLE IF NOT EXISTS sessions (
  id           TEXT        PRIMARY KEY,  -- "{owner}-{repo}-{timestamp}"
  repo_url     TEXT        NOT NULL,
  repo_name    TEXT        NOT NULL,
  branch       TEXT        NOT NULL DEFAULT '',
  pr_url       TEXT,
  status       TEXT        NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'done', 'error')),
  trigger      TEXT        NOT NULL DEFAULT 'manual'
    CHECK (trigger IN ('manual', 'webhook', 'cron')),
  result       JSONB,                    -- full AnalysisResult object
  started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

-- RA-1407 — Session checkpointing for cross-deploy persistence (Option B).
-- The original status check accepted only running/done/error, but the
-- autonomous build pipeline uses a richer lifecycle (created, cloning,
-- building, evaluating, complete, failed, killed, interrupted, blocked).
-- Drop the strict constraint and add a `checkpoint` JSONB column to hold
-- last_completed_phase + retry_count + evaluator_status/score/model + linear
-- + workspace + error so a fresh container can resume.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS checkpoint JSONB;
ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_status_check;

CREATE INDEX IF NOT EXISTS sessions_started_at_idx ON sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_repo_name_idx  ON sessions (repo_name);
-- RA-1407 — Status index so startup recovery can quickly find interrupted rows.
CREATE INDEX IF NOT EXISTS sessions_status_idx     ON sessions (status);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON sessions FOR SELECT USING (true);
CREATE POLICY "service_write"  ON sessions FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "service_update" ON sessions FOR UPDATE TO service_role USING (true);

-- ── RA-1439 — cron_state ─────────────────────────────────────────────────────
-- Persistent last_fired_at per trigger, durable across Railway redeploys.
-- The schedule definitions live in `.harness/cron-triggers.json` (committed).
-- The runtime `last_fired_at` lives HERE so Railway deploys don't reset it
-- to the frozen git state. Without this, every redeploy reverts every
-- trigger's last_fired_at to whatever was committed, defeating catch-up
-- because the next deploy reverts again before save_triggers persists.
CREATE TABLE IF NOT EXISTS cron_state (
  trigger_id     TEXT        PRIMARY KEY,
  last_fired_at  TIMESTAMPTZ NOT NULL,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE cron_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cron_state_public_read"    ON cron_state;
DROP POLICY IF EXISTS "cron_state_service_write"  ON cron_state;
DROP POLICY IF EXISTS "cron_state_service_update" ON cron_state;
CREATE POLICY "cron_state_public_read"    ON cron_state FOR SELECT USING (true);
CREATE POLICY "cron_state_service_write"  ON cron_state FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "cron_state_service_update" ON cron_state FOR UPDATE TO service_role USING (true);

-- ── terminal_lines ────────────────────────────────────────────────────────────
-- Persisted terminal output lines per session (enables replay on reconnect)
CREATE TABLE IF NOT EXISTS terminal_lines (
  id         BIGSERIAL   PRIMARY KEY,
  session_id TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  type       TEXT        NOT NULL
    CHECK (type IN ('phase','tool','agent','success','error','system','output')),
  text       TEXT        NOT NULL,
  ts         FLOAT8      NOT NULL,  -- Unix timestamp seconds (matches TermLine.ts)
  seq        INTEGER     NOT NULL   -- ordering within session
);

CREATE INDEX IF NOT EXISTS terminal_lines_session_idx ON terminal_lines (session_id, seq);

ALTER TABLE terminal_lines ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON terminal_lines FOR SELECT USING (true);
CREATE POLICY "service_insert" ON terminal_lines FOR INSERT TO service_role WITH CHECK (true);

-- ── phase_states ──────────────────────────────────────────────────────────────
-- Phase status per session (enables progress replay)
CREATE TABLE IF NOT EXISTS phase_states (
  session_id TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  phase_id   INTEGER     NOT NULL,
  status     TEXT        NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'done', 'error')),
  started_at TIMESTAMPTZ,
  done_at    TIMESTAMPTZ,
  PRIMARY KEY (session_id, phase_id)
);

ALTER TABLE phase_states ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON phase_states FOR SELECT USING (true);
CREATE POLICY "service_insert" ON phase_states FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "service_update" ON phase_states FOR UPDATE TO service_role USING (true);

-- ── gate_checks ───────────────────────────────────────────────────────────────
-- RA-651: Records every quality gate evaluation from the ship-chain.
-- Drives Operational Observability on the Command Centre dashboard.
CREATE TABLE IF NOT EXISTS gate_checks (
  id              BIGSERIAL    PRIMARY KEY,
  pipeline_id     TEXT         NOT NULL,
  session_id      TEXT,
  spec_exists     BOOLEAN      NOT NULL DEFAULT FALSE,
  plan_exists     BOOLEAN      NOT NULL DEFAULT FALSE,
  build_complete  BOOLEAN      NOT NULL DEFAULT FALSE,
  tests_passed    BOOLEAN      NOT NULL DEFAULT FALSE,
  review_passed   BOOLEAN      NOT NULL DEFAULT FALSE,
  all_passed      BOOLEAN      NOT NULL DEFAULT FALSE,
  review_score    FLOAT8,
  shipped         BOOLEAN      NOT NULL DEFAULT FALSE,
  checked_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gate_checks_checked_at_idx  ON gate_checks (checked_at DESC);
CREATE INDEX IF NOT EXISTS gate_checks_pipeline_id_idx ON gate_checks (pipeline_id);

ALTER TABLE gate_checks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON gate_checks FOR SELECT USING (true);
CREATE POLICY "service_insert" ON gate_checks FOR INSERT TO service_role WITH CHECK (true);

-- RA-672: ZTE v2 timing columns — trigger-to-deploy measurement (C3)
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS session_started_at TIMESTAMPTZ;
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS push_timestamp TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS gate_checks_push_ts_idx ON gate_checks (push_timestamp DESC) WHERE push_timestamp IS NOT NULL;

-- RA-674: evaluator confidence score (0–100%) per gate_check
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS confidence FLOAT8;

-- RA-676: scope contract tracking
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS scope_adhered BOOLEAN;
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS files_modified INTEGER;

-- RA-672 C2: Linear issue state at push time — persists across Railway redeploys
-- session-outcomes.jsonl is ephemeral in Railway containers; this column makes
-- C2 (output acceptance) scoring durable.
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS linear_state_after TEXT;
CREATE INDEX IF NOT EXISTS gate_checks_linear_state_idx ON gate_checks (linear_state_after) WHERE linear_state_after IS NOT NULL;

-- ── alert_escalations ────────────────────────────────────────────────────────
-- RA-633: Tracks critical alerts sent via Telegram + escalation/ack state.
-- Enables the 30-min escalation watchdog: unacked alerts → second louder page.
CREATE TABLE IF NOT EXISTS alert_escalations (
  id               BIGSERIAL    PRIMARY KEY,
  alert_key        TEXT         NOT NULL UNIQUE,   -- finding fingerprint or Linear ticket ID
  project_id       TEXT         NOT NULL,
  issue_title      TEXT         NOT NULL,
  severity         TEXT         NOT NULL DEFAULT 'critical',
  linear_ticket    TEXT,
  telegram_sent    BOOLEAN      NOT NULL DEFAULT FALSE,
  telegram_sent_at TIMESTAMPTZ,
  escalated        BOOLEAN      NOT NULL DEFAULT FALSE,
  escalated_at     TIMESTAMPTZ,
  acked            BOOLEAN      NOT NULL DEFAULT FALSE,
  acked_at         TIMESTAMPTZ,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alert_escalations_unacked_idx
  ON alert_escalations (telegram_sent_at)
  WHERE telegram_sent = TRUE AND escalated = FALSE AND acked = FALSE;

ALTER TABLE alert_escalations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON alert_escalations FOR SELECT USING (true);
CREATE POLICY "service_insert" ON alert_escalations FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "service_update" ON alert_escalations FOR UPDATE TO service_role USING (true);

-- ── telegram_sessions ─────────────────────────────────────────────────────────
-- RA-924 — Durable Telegram bot session store.
-- Replaces the ephemeral SQLite DB so Claude session IDs survive Railway redeploys.
-- Each row maps a Telegram user_id to a Claude Code session_id for a given project.
-- The SupabaseSessionStorage class in telegram-bot/src/storage/ reads/writes this table.
CREATE TABLE IF NOT EXISTS telegram_sessions (
  session_id    TEXT        PRIMARY KEY,           -- Claude SDK session ID
  user_id       BIGINT      NOT NULL,               -- Telegram user ID
  project_path  TEXT        NOT NULL,               -- working directory path
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used     TIMESTAMPTZ NOT NULL DEFAULT now(),
  total_cost    REAL        NOT NULL DEFAULT 0.0,
  total_turns   INTEGER     NOT NULL DEFAULT 0,
  message_count INTEGER     NOT NULL DEFAULT 0,
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS telegram_sessions_user_id_idx
  ON telegram_sessions (user_id)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS telegram_sessions_last_used_idx
  ON telegram_sessions (last_used DESC)
  WHERE is_active = TRUE;

ALTER TABLE telegram_sessions ENABLE ROW LEVEL SECURITY;
-- Service role only — anon clients must never read Telegram user mappings.
CREATE POLICY "service_only" ON telegram_sessions FOR ALL TO service_role USING (true);

-- ── RA-931: build_episodes ────────────────────────────────────────────────────
-- Experience Recorder: stores structured build run data for context replay.
-- Trust anchor: only verified=true rows are injected as context (AgentRR pattern).
-- embedding column uses pgvector (1536-dim) — requires vector extension.
-- Add via Supabase dashboard: Extensions → vector → Enable.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS build_episodes (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       TEXT        NOT NULL,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  task_type        TEXT,                         -- 'add_feature', 'fix_bug', 'refactor', 'docs', 'test'
  repo_url         TEXT,
  files_touched    TEXT[]      DEFAULT '{}',     -- git diff --stat file list
  outcome          TEXT,                         -- 'complete', 'failed', 'interrupted'
  evaluator_score  FLOAT,
  tests_passed     BOOL        DEFAULT FALSE,
  verified         BOOL        DEFAULT FALSE,    -- TRUE only when outcome=complete AND tests_passed
  duration_s       INT,
  error_patterns   TEXT[]      DEFAULT '{}',
  git_diff_summary TEXT,
  heuristics       TEXT[]      DEFAULT '{}',     -- async-populated by future Haiku pass
  embedding        VECTOR(1536)                  -- pgvector: task description embedding
);

-- Fast recency+repo lookups (primary query pattern)
CREATE INDEX IF NOT EXISTS build_episodes_repo_verified_idx
  ON build_episodes (repo_url, verified, created_at DESC);

-- pgvector cosine similarity index (ivfflat — needs ≥100 rows to be useful)
-- CREATE INDEX build_episodes_embedding_idx
--   ON build_episodes USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists = 100);
-- ↑ Uncomment after 100+ episodes are recorded.

ALTER TABLE build_episodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only" ON build_episodes FOR ALL TO service_role USING (true);

-- ── RA-820: notebooklm_health ─────────────────────────────────────────────────
-- Health probe results for active NotebookLM knowledge bases.
-- Written by _watchdog_notebooklm_health() in cron_watchdogs.py every 6 hours.
-- Telegram alert fires when any notebook returns status = 'failed' or 'timeout'.
CREATE TABLE IF NOT EXISTS notebooklm_health (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  notebook_id    TEXT        NOT NULL,
  notebook_name  TEXT        NOT NULL,
  query_hash     TEXT        NOT NULL,    -- MD5 of query string for dedup analytics
  status         TEXT        NOT NULL CHECK (status IN ('ok', 'failed', 'timeout')),
  error_message  TEXT,
  response_ms    INTEGER,
  checked_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notebooklm_health_notebook_idx
  ON notebooklm_health (notebook_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS notebooklm_health_failures_idx
  ON notebooklm_health (status, checked_at DESC)
  WHERE status != 'ok';

ALTER TABLE notebooklm_health ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON notebooklm_health FOR SELECT USING (true);
CREATE POLICY "service_insert" ON notebooklm_health FOR INSERT TO service_role WITH CHECK (true);
