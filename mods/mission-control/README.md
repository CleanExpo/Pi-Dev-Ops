# mission-control

Read-only Claude Code mod that shows the fleet from `GET /api/mesh/fleet`:

- **`/mc`** opens a pane: one row per machine (host, status, heartbeat age), with
  stale, `runner-down` and `offline` rows in red; the open-claim count; the last
  five ships; and a red banner when the read is **degraded** or **unknown**. It
  reads on open and every 30 s while the pane is open (`r` refreshes; Esc closes
  and stops the timer).
- **`fleet_status`** tool (Claude sees `mcp__mission-control__fleet_status`, no
  input) returns the same summary as compact JSON text.

A failed, refused (401), non-JSON or server-degraded read is shown as
`unknown`/`degraded` with the reason. It is never an empty healthy fleet.
Nothing is written anywhere.

Server: `app/server/routes/mesh.py` `fleet()` · snapshot: `app/server/mesh_fleet.py`
· auth: `app/server/mesh_fleet_auth.py` · Mods docs: `docs/reference/claude-mods/`

## Configure (per machine), the same variables as mc-lane

| Variable | Value |
|---|---|
| `MC_LANE_URL` | Pi-CEO backend base URL |
| `MC_LANE_SECRET` | the `X-Pi-CEO-Secret` the fleet already uses (the fleet read accepts it) |

Unset URL or secret → `/mc` and the tool answer
`mission-control not configured: MC_LANE_URL / MC_LANE_SECRET unset` and nothing is fetched.

## Check and test

```bash
claude plugin validate mods/mission-control
claude plugin test mods/mission-control
```

## Install

```bash
claude plugin marketplace add CleanExpo/Pi-Dev-Ops
claude plugin install mission-control@pi-dev-ops-mods
```

No `version` in `plugin.json`, so merged changes reach machines with auto-update on at the next session start.

## Try it in one session

```bash
MC_LANE_URL=... MC_LANE_SECRET=... claude --plugin-dir mods/mission-control
```
