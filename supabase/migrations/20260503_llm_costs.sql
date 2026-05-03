-- RA-1909 — LLM cost tracking table.
-- Mirror of swarm/budget_tracker.py JSONL writes; survives Railway redeploys.
create table if not exists llm_costs (
  id bigserial primary key,
  ts timestamptz not null default now(),
  tenant_id text not null default 'pi-ceo',
  provider text not null,
  role text,
  model text,
  cost_usd numeric(10,6) not null,
  tokens_in int,
  tokens_out int
);
create index if not exists llm_costs_ts_idx on llm_costs (ts desc);
create index if not exists llm_costs_tenant_idx on llm_costs (tenant_id, ts desc);
