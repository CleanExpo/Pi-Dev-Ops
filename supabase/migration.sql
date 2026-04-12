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

CREATE INDEX IF NOT EXISTS sessions_started_at_idx ON sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_repo_name_idx  ON sessions (repo_name);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read"    ON sessions FOR SELECT USING (true);
CREATE POLICY "service_write"  ON sessions FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "service_update" ON sessions FOR UPDATE TO service_role USING (true);

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
