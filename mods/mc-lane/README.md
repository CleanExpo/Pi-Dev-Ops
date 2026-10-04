# mc-lane

Claude Code mod that reports each lane to Mission Control: session start/end,
each tool call's **name, ok/failed and duration**, and context %, worst
rate-limit % and cost after each turn. No tool input or output leaves the machine.

Spec: `docs/specs/claude-mods-integration.md` §3.1 · Server: `app/server/routes/mesh_lane_events.py`
· Table: `mesh/schema/0004_mesh_lane_events.sql` · Mods docs: `docs/reference/claude-mods/`

## Configure (per machine)

| Variable | Value |
|---|---|
| `MC_LANE_URL` | Pi-CEO backend base URL |
| `MC_LANE_SECRET` | the `X-Pi-CEO-Secret` the fleet already uses for heartbeats |
| `MC_LANE_HOST` | this machine's fleet name, as in `mesh_machines.host` |

Unset URL or secret → the mod sends nothing and logs one line saying so.

## Check and test

```bash
claude plugin validate mods/mc-lane
claude plugin test mods/mc-lane
```

## Try it in one session (before any install)

```bash
MC_LANE_URL=... MC_LANE_SECRET=... MC_LANE_HOST=unite-mac-mini claude --plugin-dir mods/mc-lane
```

Fleet install goes through `unite-group-marketplace` once the table is applied
and a Mission Control module reads `GET /api/mesh/lane-events`.
