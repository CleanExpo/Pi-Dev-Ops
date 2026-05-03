-- RA-1905: Persistent Margot conversation memory (survives Railway redeploys).
--
-- Founder reported "memory not picking up the text thread" on 2026-05-03.
-- Root cause: .harness/margot/conversations/<chat>.jsonl lives on Railway
-- ephemeral disk and was wiped by every redeploy. JSONL stays as a hot local
-- cache; this table is the durable source of truth read on rehydrate.
--
-- tenant_id default 'pi-ceo' is forward-compat per RA-1838 (per-tenant verdict).

create table if not exists margot_conversations (
  turn_id text primary key,
  chat_id text not null,
  tenant_id text not null default 'pi-ceo',
  user_text text,
  margot_text text,
  user_message_id text,
  board_session_ids jsonb default '[]'::jsonb,
  research_called boolean default false,
  cost_usd float8 default 0.0,
  started_at timestamptz,
  ended_at timestamptz,
  error text,
  created_at timestamptz not null default now()
);

create index if not exists margot_conversations_chat_started_idx
  on margot_conversations (tenant_id, chat_id, started_at desc);
