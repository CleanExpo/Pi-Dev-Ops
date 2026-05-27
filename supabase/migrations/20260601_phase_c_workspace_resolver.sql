-- Phase C / C2 — Workspace resolver support.
-- Adds stripe_customer_id to client_workspaces so the resolver can map
-- Stripe webhook payloads (which carry customer.id, not workspace_slug)
-- back to the right workspace.
--
-- Additive + nullable: safe to roll forward, safe to leave on rollback.
--
-- Rollback:
--   alter table public.client_workspaces drop column if exists stripe_customer_id;

alter table public.client_workspaces
  add column if not exists stripe_customer_id text;

create index if not exists client_workspaces_stripe_customer_idx
  on public.client_workspaces (stripe_customer_id)
  where stripe_customer_id is not null;

-- Verification:
--   select column_name, is_nullable, data_type
--   from information_schema.columns
--   where table_schema='public' and table_name='client_workspaces'
--     and column_name='stripe_customer_id';
--   -- expects one row, is_nullable='YES', data_type='text'
