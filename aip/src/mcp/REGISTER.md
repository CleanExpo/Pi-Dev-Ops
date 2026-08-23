# Registering the AIP MCP server with Claude Code

Register the wrapper with the Claude Code CLI:

```bash
claude mcp add --scope local aip-readonly -- <absolute-path-to-repo>/aip/src/mcp/run.sh
```

That writes the entry to `~/.claude.json`. MCP servers live there (local and user
scope) or in a project `.mcp.json`. Do **not** put them in
`~/.claude/settings.local.json` — Claude Code does not read MCP configuration from
that file, and a server registered there is silently never discovered.

Register `run.sh`, not `server.ts` directly. The wrapper exports
`SUPABASE_PICEO_URL` and resolves the service-role key from 1Password itself, so
the entry needs no `env` block. Supplying `SUPABASE_PICEO_SERVICE_KEY` here as an
unresolved `op://...` reference does not work — `server.ts` rejects it.

## Prerequisite — the headless 1Password token

`run.sh` reads the service-role key at every launch via `op read`, so no secret is
ever placed in a config file or a shell profile. It needs two things present:

- The `op` CLI on `PATH`.
- A 1Password service-account token named `OP_SERVICE_ACCOUNT_TOKEN_NEXUS_AUDIT`
  in `~/.hermes/.env` (override with `AIP_OP_SERVICE_ACCOUNT_ENV_FILE`). The
  wrapper refuses to run unless that file is owned by you and has mode `600` or
  `400`, and it unsets the token before exec'ing the server.

This exists because Claude's GUI-launched MCP processes do not inherit shell
startup files, so a key exported in `~/.zshrc` is not visible to them.

Do not paste the resolved key into the registration snippet. Retrieving a live
credential by hand to paste it somewhere is the failure this wrapper removes.

## Verify

Restart Claude Code, then:

```
/mcp
```

You should see `aip-readonly` listed with 5 tools:
`aip_get_entity`, `aip_list_entities`, `aip_traverse`, `aip_query_view`,
`aip_log_tail`.

Quick functional check from inside Claude Code:

> Use the `aip_list_entities` tool with `{ "kind": "PortfolioService" }`.

Expected: at least the seeded RestoreAssist (`aip://unite-group/PortfolioService/ra`).
