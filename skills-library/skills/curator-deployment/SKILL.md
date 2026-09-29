---
name: curator-deployment
description: Use when deploying services, merging PRs, configuring CI pipelines, or setting up tunnel/process launchers. Catches empty inherited API keys, stale Vercel rootDirectory, unsupported GitHub Actions, missing branch protection checks, and incomplete LaunchAgent plists before they cause silent failures in production.
owner_role: deployment-engineer
status: active
---

# curator-deployment

## Why this exists

Five recurring deployment failures were independently observed across unrelated repos and contexts. Each caused silent or confusing breakage that looked like an infrastructure fault rather than a configuration mistake. This skill consolidates the detection and fix pattern for each into a single pre-deploy and pre-merge checklist.

Failure modes covered:

1. `ANTHROPIC_API_KEY=""` inherited by subprocesses — the claude CLI injects an empty-string key into the shell env; child processes treat the empty string as "key provided but invalid" and fail with HTTP 401 instead of falling back to OAuth tokens.
2. `dependency-review-action@v4` in GitHub Actions on repos without GitHub Advanced Security — the action exits with "Dependency review is not supported on this repo" and blocks CI for no benefit.
3. Stale Vercel `rootDirectory` config — set during a monorepo phase, never cleared after the repo was flattened; Vercel builds from the wrong directory and silently deploys a broken or empty artifact.
4. Branch protection required-checks not consulted before a PR merge attempt — the merge fails or bypasses required gates, causing a surprise block or a mis-merge.
5. macOS LaunchAgent plist for cloudflared missing the `tunnel` subcommand args — launchd starts the binary, the binary exits immediately, no tunnel runs, no error surfaced to the operator.

## When to use

- Before opening or merging any PR that touches CI workflow files, Vercel config, or service launch scripts.
- When setting up a new GitHub Actions workflow on any repo.
- When a subprocess or spawned service is failing auth and `ANTHROPIC_API_KEY` is set in the shell.
- When configuring or updating a macOS LaunchAgent that wraps a CLI tool.
- When the Vercel deploy succeeds but the deployed artifact is empty or wrong.
- When a PR merge is blocked by unexpected required-check failures.

## When NOT to use

- Pure application-logic changes with no deployment surface (no CI, no env, no Vercel config, no plist).
- Debugging runtime errors unrelated to configuration (use `superpowers:systematic-debugging` instead).
- Repos where none of these tools (Vercel, cloudflared, Anthropic SDK, GitHub Actions) are in use.

## Pipeline

Run each check that applies to the current change. Skip sections that are irrelevant to the repo.

### 1. Clear empty ANTHROPIC_API_KEY before spawning subprocesses

Detect whether the key is an empty string (not unset) before any subprocess call:

```python
import os

key = os.environ.get("ANTHROPIC_API_KEY", "")
if not key:
    os.environ.pop("ANTHROPIC_API_KEY", None)
# Subprocess now falls back to ~/.claude/ OAuth tokens
```

For shell scripts, check before exec:

```bash
[ -z "$ANTHROPIC_API_KEY" ] && unset ANTHROPIC_API_KEY
```

Apply this pattern at every call site that spawns a Claude subprocess or calls the Anthropic SDK without an explicit key argument.

### 2. Validate GitHub Actions before adding dependency-review-action

Before adding `dependency-review-action` to a workflow:

```bash
gh api repos/OWNER/REPO \
  --jq '.security_and_analysis.dependency_graph.status // "disabled"'
```

If the output is `disabled` or the repo is on a free plan, remove or comment out the `dependency-review` step. Replace with a lighter alternative such as `npm audit --audit-level=high` if dependency scanning is still required.

### 3. Verify Vercel rootDirectory matches current repo layout

```bash
vercel project ls  # confirm project name
vercel project inspect PROJECT_NAME | grep -i root
```

If `rootDirectory` is set and the directory no longer exists at that path, clear it:

```bash
vercel project update PROJECT_NAME --root-directory ""
```

Then trigger a fresh deploy and confirm the build log shows files from the actual repo root.

### 4. Check branch protection before merging a PR

```bash
gh api repos/OWNER/REPO/branches/main/protection \
  --jq '.required_status_checks.contexts[]'
```

Cross-reference the output against `gh pr checks PR_NUMBER`. Every context listed by the protection API must be green before attempting merge. If a required check is missing from the PR, trace why it did not run (wrong trigger, path filter, or job name mismatch) before merging.

### 5. Validate cloudflared LaunchAgent plist completeness

Open the plist and confirm `ProgramArguments` includes the full subcommand chain:

```bash
plutil -p ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist \
  | grep -A 10 ProgramArguments
```

A correct entry looks like:

```
"ProgramArguments" => [
  "/usr/local/bin/cloudflared",
  "tunnel",
  "--config", "/path/to/config.yml",
  "run"
]
```

If `tunnel` is absent, add it. After editing, reload:

```bash
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
launchctl load  ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
launchctl list | grep cloudflared  # PID column must be non-zero
```

## Verification

After applying fixes:

| Check | Pass condition |
|---|---|
| Subprocess auth | `claude -p "ping"` from a shell where `ANTHROPIC_API_KEY` is unset succeeds without 401 |
| CI dependency-review | Workflow run completes green; no "not supported" error in the step log |
| Vercel rootDirectory | Build log first line shows files from repo root, not a subdirectory |
| Branch protection | `gh pr checks PR_NUMBER` shows all required contexts green before merge |
| cloudflared LaunchAgent | `launchctl list | grep cloudflared` shows a non-zero PID within 5 s of load |

File a Linear ticket for any check that cannot be made to pass within the current session. Do not mark the PR ready-to-merge until the blocking check resolves.
