-- Nexus Mesh 0002 — run records on work claims (UNI-2796).
--
-- A build run used to report only its state, so a failure's reason and the
-- agent's output stayed on the machine that ran it. These columns carry what
-- `mesh/run_record.py` reports through `/api/mesh/claim/update`.
--
-- All nullable, all additive: older runners send none of them, and
-- `app/server/mesh_run_record.patch_claim` keeps storing the state change when
-- these columns are absent, so the server can deploy before this is applied.
--
-- `log_tail` is at most 4,000 characters, redacted twice (runner, then server)
-- before it reaches this table. RLS and the service_only policy from 0001 cover
-- the new columns: they are on the same table.

alter table mesh_work_claims add column if not exists run_id     text;
alter table mesh_work_claims add column if not exists duration_s double precision;
alter table mesh_work_claims add column if not exists exit_code  integer;
alter table mesh_work_claims add column if not exists error      text;
alter table mesh_work_claims add column if not exists log_tail   text;
