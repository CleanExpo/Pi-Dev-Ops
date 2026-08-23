# Registering the AIP MCP server with Claude Code

Register the wrapper with the Claude Code CLI. Run this **from the repository
root** — `--scope local` binds the entry to the directory you run it in:

```bash
cd <absolute-path-to-repo>
claude mcp add --scope local aip-readonly -- <absolute-path-to-repo>/aip/src/mcp/run.sh
```

That writes the entry to `~/.claude.json`, under the project you ran it from, so
`aip-readonly` is visible in that project and its subdirectories and nowhere else.
Running the command from anywhere else registers it against that other directory
and Claude Code will report `No MCP server named "aip-readonly"` here — the
absolute path to `run.sh` does not make the registration location-independent. Open
the same project in the GUI. To have it everywhere instead, use `--scope user`.

MCP servers live in `~/.claude.json` (local and user scope) or in a project
`.mcp.json`. Do **not** put them in `~/.claude/settings.local.json` — Claude Code
does not read MCP configuration from that file, and a server registered there is
silently never discovered.

Register `run.sh`, not `server.ts` directly. The wrapper exports
`SUPABASE_PICEO_URL` and resolves the service-role key from 1Password itself, so
the entry needs no `env` block. Supplying `SUPABASE_PICEO_SERVICE_KEY` here as an
unresolved `op://...` reference does not work — `server.ts` rejects it.

## Prerequisite — the headless 1Password token

`run.sh` reads the Supabase service-role key at every launch via `op read`, so that
key is never written into the MCP registration or a shell profile. This is a
deliberate trade, not the removal of all stored credentials: a narrowly-scoped
1Password service-account token is still stored on disk, in a protected file, and
is what the wrapper uses to fetch the key. It needs two things present:

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
