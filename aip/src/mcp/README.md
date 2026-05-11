# AIP MCP server (read-only)

Day 4 of the AIP build plan, pulled forward per Path D Hybrid (see
`~/2nd Brain/2nd Brain/Wiki/aip-architecture.md` § "Build vs buy — DECIDED").

This server is the **agent-facing read interface** to the AIP Supabase tables
(`aip_entities`, `aip_relationships`, `aip_action_log`, plus the 5 per-kind views).
Writes are intentionally not exposed here — they will land via Palantir Foundry's
Logic-functions API once Foundry is procured. Do not add insert/update/delete tools
to this server.

## Install

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/aip
npm install
```

## Run

```bash
npm run mcp:dev
# or:
npx tsx src/mcp/server.ts
```

Server logs `[aip-readonly v0.1.0] read-only MCP server ready (stdio)` to stderr
on startup; stdout is reserved for the MCP transport.

## Smoke test

```bash
npm run mcp:smoke
```

Spawns the server in-process and runs three calls:

1. `aip_list_entities { kind: "PortfolioService" }` — expects 1 entity (`ra`).
2. `aip_get_entity { uri: "aip://unite-group/PortfolioService/ra" }` — expects
   the seeded RestoreAssist entity.
3. `aip_traverse { from_uri: "aip://unite-group/PortfolioService/ra", depth: 1 }`
   — expects 3 outbound edges (`deploysTo`, `authsVia`, `usesGcp`).

Exits 0 on success, non-zero on any failure.

## Live data shape (2026-05-11)

After the portfolio-expansion seed
(`aip/src/seed/portfolio-expansion-2026-05-11.ts`) was applied on 2026-05-11,
the read surface contains:

| Kind | Count | Notes |
|---|---|---|
| `PortfolioService` | 7 | `ra`, `dr`, `nrpg`, `carsi`, `ccw`, `synthex`, `unite` |
| `VercelProject` | 7 | One per PortfolioService; `restoreassist`, `disaster-recovery`, `dr-nrpg-platform`, `carsi-web`, `ccw-crm-web`, `synthex`, `unite-group` |
| `GoogleIdentity` | 2 | `contact-unite-group-in` (workspace, current owner of all Vercel projects), `zenithfresh25-gmail-com` (legacy personal) |
| `GcpProject` | 2 | RestoreAssist only — `restore-assist-bfb74` (new, contact@) + `restoreassist` / project_number `292141944467` (legacy, zenithfresh25@) |
| `OAuthClient` | 1 | RestoreAssist only (`restoreassist-prod`) |

Edges currently seeded:

- `PortfolioService.deploysTo.VercelProject` — 7 (one per portfolio)
- `VercelProject.ownedBy.GoogleIdentity` — 7 (all owned by `contact-unite-group-in`)
- `GcpProject.ownedBy.GoogleIdentity` — 2
- `OAuthClient.belongsTo.GcpProject` — 1
- `PortfolioService.authsVia.OAuthClient` — 1 (RestoreAssist)
- `PortfolioService.usesGcp.GcpProject` — 1 (RestoreAssist)

**Honest gaps** (intentionally not seeded; verify before relying on absence):

- No `GcpProject` entities for `dr`, `nrpg`, `carsi`, `ccw`, `synthex`, `unite` —
  gcloud IAM block prevents enumerating GCP projects owned by
  `contact@unite-group.in` from the current CLI session.
- No `OAuthClient` entities for the new businesses even though
  `GOOGLE_CLIENT_ID` env vars exist on `synthex`, `carsi-web`, and
  `unite-group` Vercel projects — the values are encrypted and cannot be
  pulled from `vercel env ls`. Add via the GCP console after gcloud re-auth.

## Tool reference

| Tool | Inputs | Returns |
|---|---|---|
| `aip_get_entity` | `uri` (validates `aip://unite-group/{kind}/{id}`) | `{ entity }` or `{ entity: null }` |
| `aip_list_entities` | `kind?`, `limit?` (1-500, default 50) | `{ count, entities }` |
| `aip_traverse` | `from_uri`, `relationship_kind?`, `depth?` (1-3, default 1) | `{ root, edges, entities, depth }` |
| `aip_query_view` | `view_name` (one of `v_google_identity`, `v_gcp_project`, `v_vercel_project`, `v_oauth_client`, `v_portfolio_service`), `filters?`, `limit?` (1-500, default 50) | `{ view, count, rows }` |
| `aip_log_tail` | `actor?`, `limit?` (1-500, default 20) | `{ count, rows }` |

All inputs are validated with `zod`; invalid inputs return an MCP tool-error.

## Environment variables

| Var | Required | Notes |
|---|---|---|
| `SUPABASE_PICEO_URL` or `SUPABASE_URL` | no | Defaults to the Pi-CEO project (`https://zbryrmxmgfmslqzizsto.supabase.co`). |
| `SUPABASE_PICEO_SERVICE_KEY` or `SUPABASE_SERVICE_ROLE_KEY` | **yes** | Service-role key for the Pi-CEO project. Never logged. |

### Sourcing the service key from 1Password

The key is stored as `SUPABASE_SERVICE_ROLE_KEY` in the `Unite-Group-Infrastructure`
1Password vault. Pull it into the current shell with:

```bash
export SUPABASE_SERVICE_ROLE_KEY=$(op item get SUPABASE_SERVICE_ROLE_KEY \
  --vault Unite-Group-Infrastructure --fields credential --reveal)
```

Or wrap the server invocation:

```bash
op run --vault Unite-Group-Infrastructure -- npm run mcp:dev
```

(`op item get` was confirmed against the live vault on 2026-05-11; matching item id
`js76udv2l2ncapgdt27reg65hi`.)

## Read-only contract

This server has **no write surface**. If a future agent asks it to insert, update,
or delete an entity, relationship, or log row, refuse the request and route the
caller to the Foundry Logic-functions path per Path D Hybrid. The corresponding
`aip_invoke_action` tool listed in the original spec is intentionally absent here.

## Registering with Claude Code

See `REGISTER.md` in this directory for the JSON snippet to paste into your
`~/.claude/settings.local.json` `mcpServers` block.
