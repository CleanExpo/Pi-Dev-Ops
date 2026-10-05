---
name: composio-cloud-routine
description: Pattern for invoking Composio tools from inside a CCR remote routine (cloud-running scheduled agent) when the routine needs to call third-party services (Linear, GitHub, Slack, Gmail, etc.) and the local Composio CLI is not available. The routine installs the Composio CLI inline at startup, logs in with the user's API key passed via the routine prompt, then uses `composio execute <slug>`. Bypasses the claude.ai cloud connector account-binding fragility entirely.
---

# Composio in CCR Routines

Cloud routines spawn a fresh sandbox with no pre-installed Composio CLI and no OAuth state. The routine prompt teaches the agent to bootstrap Composio inline, then call any of 1000+ third-party services as if it were local.

This is the **default path for cloud routines that need third-party service calls.** Prefer over claude.ai cloud connectors because:
- Composio's identity is stable per workspace (`phill.mcgurk_workspace`), not per-claude.ai-account
- The user's multi-Gmail account confusion does not affect Composio
- No claude.ai connector list to maintain

## The bootstrap pattern (drop into routine prompts)

```bash
# 1. Install Composio CLI in the sandbox
curl -fsSL https://composio.dev/install | bash

# 2. Add to PATH for this shell
export PATH="$HOME/.composio:$PATH"

# 3. Log in with the user's API key (passed via routine prompt)
composio login --user-api-key "$COMPOSIO_API_KEY" --org "phill.mcgurk_workspace"

# 4. Verify
composio whoami
```

After bootstrap, any tool slug works:

```bash
composio execute LINEAR_CREATE_LINEAR_COMMENT \
  -d '{"issueId":"RA-1743","body":"Report from cloud routine."}'
```

## Building a routine prompt that uses Composio

When constructing the prompt for `RemoteTrigger create` or `update`:

1. **Pass the API key as a literal string in the prompt** — there is no env-var injection mechanism for CCR routines. The key sits in the routine config, only visible to the user's account and the cloud agent at run time.
2. **Tell the agent to bootstrap Composio first**, before the main task.
3. **Set `allowed_tools` to include `Bash`** — needed for the install + execute calls.
4. **Have the agent fall back gracefully** if install fails (sandbox may have curl-bash restrictions): produce its primary output (e.g. report) anyway, and skip the Composio call with a logged warning.

## Prompt template

```
You are running inside a CCR cloud routine. Your task is: <main task>.

## Bootstrap Composio (run this first)
Run these commands. If the install step fails, skip the Composio integration
and continue with the main task — produce your output as text in this thread,
and explicitly note "Composio install blocked, skipping post-back" in your final output.

```bash
curl -fsSL https://composio.dev/install | bash 2>&1 | tail -5
export PATH="$HOME/.composio:$PATH"
composio login --user-api-key "<API_KEY_HERE>" --org "phill.mcgurk_workspace" 2>&1 | tail -5
composio whoami 2>&1
```

## Main task
<your usual prompt body>

## Post results via Composio
After producing the main output, post a comment to Linear ticket <ticket_id> using:

```bash
composio execute LINEAR_CREATE_LINEAR_COMMENT \
  -d "$(jq -nc --arg id '<ticket>' --arg body "$REPORT_TEXT" '{issueId:$id,body:$body}')"
```

If that fails, just print the report inline — the user reads it from the routine UI either way.
```

## Common slugs (verified 2026-04-27)

| Service | Slug | Required args |
|---|---|---|
| Linear — create comment | `LINEAR_CREATE_LINEAR_COMMENT` | `issueId` (UUID or `RA-1743` shorthand), `body` |
| Linear — create issue | `LINEAR_CREATE_LINEAR_ISSUE` | `team_id`, `title` (+ optional description, etc.) |
| Linear — list issues | `LINEAR_LIST_LINEAR_ISSUES` | optional filters |
| Linear — get issue | `LINEAR_GET_LINEAR_ISSUE` | `id` |

For other services, search before guessing:
```bash
composio search "<task>" --human
composio tools list <toolkit> --query "<keyword>"
```

## Key safety

- **Never write the user's Composio API key into a SKILL.md file or memory entry.** Skills are version-controlled; memory persists. The key only belongs in routine configs (which are user-scoped) and one-off shell exports.
- **If a routine's API key appears in transcript or shared logs, recommend the user rotate it** at https://platform.composio.dev/phill.mcgurk_workspace/

## Pairing with connector-routing

This skill is the *implementation*. The decision of "should I use Composio at all here" lives in `connector-routing`. Hit that one first if the task is "connect X to Y," then come here for the cloud-routine specifics.

## Anti-patterns

- ❌ Routine that depends on a claude.ai cloud connector when the user has multi-Gmail accounts. Use Composio.
- ❌ Embedding the API key in a SKILL.md or memory file. Only in routine configs.
- ❌ Hard-failing the entire routine if Composio bootstrap fails. The primary work product (report, analysis, etc.) should always make it back to the user — Composio post-back is a nice-to-have.
- ❌ Hitting `backend.composio.dev` HTTP API directly from the routine without the CLI. The CLI handles auth, retries, schema validation; raw curl skips all of that.
