-- Nexus Mesh 0005 — mesh_lane_events accepts kind 'agent_start' (RA-7923).
--
-- The mc-lane mod records a subagent or agent-team teammate start (its
-- agent.spawn hook) as kind 'agent_start': the agent type's name in `tool`,
-- the model it started on in `model`, ok = true. Nothing else; no new column.
--
-- ORDER. Apply this BEFORE the backend that accepts 'agent_start' deploys.
-- Until it is applied, a batch holding an agent_start row fails the CHECK, the
-- POST answers 502, and the lane keeps (and retries) the whole batch, so its
-- other events stall behind it too.
--
-- Numbering: check production's migration ledger for a `nexus_mesh_0005*`
-- entry before applying (see 0004's header). Rename this file if 0005 is taken.
--
-- Idempotent: drops the 0004 check (Postgres' default name for it) and adds the
-- wider one under the same name.

alter table mesh_lane_events drop constraint if exists mesh_lane_events_kind_check;
alter table mesh_lane_events add constraint mesh_lane_events_kind_check
  check (kind in ('session_start','tool','agent_start','usage','session_end'));
