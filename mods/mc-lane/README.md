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

## Install (every machine) — updates arrive on their own

This repository is a marketplace (`.claude-plugin/marketplace.json`, name `pi-dev-ops-mods`).
It is public, so background auto-update needs no credentials.

```bash
claude plugin marketplace add CleanExpo/Pi-Dev-Ops
claude plugin install mc-lane@pi-dev-ops-mods
```

Then turn on auto-update for `pi-dev-ops-mods` (`/plugin` → Marketplaces → Enable auto-update,
or `"autoUpdate": true` on its `extraKnownMarketplaces` entry). There is no `version` in
`plugin.json`, so every merged change to `mods/mc-lane` reaches the fleet at the next session start.

## Try it in one session (before any install)

```bash
MC_LANE_URL=... MC_LANE_SECRET=... MC_LANE_HOST=unite-mac-mini claude --plugin-dir mods/mc-lane
```

