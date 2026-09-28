-- Nexus Mesh 0003 — run records on work claims (UNI-2796).
--
-- Numbered 0003, not 0002: production's migration ledger already holds
-- `nexus_mesh_0002_rls` (applied 2026-06-11, no file in this repo), so a
-- second 0002 would make the ledger and this directory disagree on what
-- 0002 means.
--
-- A build run used to report only its state, so a failure's reason and the
-- agent's output stayed on the machine that ran it. These columns carry what
-- `mesh/run_record.py` reports through `/api/mesh/claim/update`.
--
-- All nullable, all additive: older runners send none of them, and
-- `app/server/mesh_run_record.patch_claim` keeps storing the state change when
-- these columns are absent, so the server can deploy before this is applied.
--
-- No free text is stored: `error_code` is one of six literals (agent_exit,
-- timeout, repo_missing, worktree_add_failed, runner_exception, runner_exception_os),
-- validated by app/server/mesh_run_record.py. The agent's transcript and the
-- full error text stay on the node that ran it (see mesh/run_record.py).
-- RLS and the service_only policy from 0001 cover the new columns: they are
-- on the same table.

alter table mesh_work_claims add column if not exists run_id     text;
alter table mesh_work_claims add column if not exists duration_s double precision;
alter table mesh_work_claims add column if not exists exit_code  integer;
alter table mesh_work_claims add column if not exists error_code text;
