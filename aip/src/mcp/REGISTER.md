# Registering the AIP MCP server with Claude Code

Add this snippet to the `mcpServers` block in `~/.claude/settings.local.json`
(create the block if it doesn't exist). Do **not** check the file in.

```json
{
  "mcpServers": {
    "aip-readonly": {
      "command": "npx",
      "args": [
        "tsx",
        "/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/aip/src/mcp/server.ts"
      ],
      "env": {
        "SUPABASE_PICEO_URL": "https://zbryrmxmgfmslqzizsto.supabase.co",
        "SUPABASE_PICEO_SERVICE_KEY": "op://Unite-Group-Infrastructure/SUPABASE_SERVICE_ROLE_KEY/credential"
      }
    }
  }
}
```

## Resolving the 1Password reference

The `op://...` value above is a 1Password secret reference. Two options:

### Option A — pre-export the key in your shell profile

```bash
# in ~/.zshrc
export SUPABASE_PICEO_SERVICE_KEY=$(op item get SUPABASE_SERVICE_ROLE_KEY \
  --vault Unite-Group-Infrastructure --fields credential --reveal 2>/dev/null)
```

Then drop the `env` block from the snippet — Claude Code will inherit the env var.

### Option B — wrap with `op run`

If your Claude Code launcher already runs through `op run`, the `op://...` reference
resolves automatically. Otherwise, replace the `env.SUPABASE_PICEO_SERVICE_KEY`
value with the literal key (after retrieving it from 1Password) — but **never**
commit that file.

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

Expected: 1 entity, the seeded RestoreAssist (`aip://unite-group/PortfolioService/ra`).
