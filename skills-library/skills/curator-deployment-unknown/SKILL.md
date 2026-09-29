---
name: curator-deployment-unknown
description: Use when hitting deployment failures in GitHub Actions dependency-review, Vercel rootDirectory config after a monorepo flatten, branch protection required-status-check mismatches blocking PR merge, or a macOS LaunchAgent cloudflared tunnel that silently exits.
owner_role: curator
status: proposed
---

# curator-deployment-unknown

## Why this exists

Four deployment gotchas surfaced in sprint-12-review that each fail silently or with a misleading error. None has an obvious fix, all recur across repos, and each costs multiple hours the first time. Grouping them prevents repeat debug cycles.

## When to use

- GitHub Actions CI fails with "Dependency review is not supported on this repo"
- Vercel deployment builds but serves the wrong bundle or 404s all routes after a monorepo flatten
- A PR is blocked at merge despite all status checks appearing green in the GitHub UI
- A macOS cloudflared LaunchAgent starts but the tunnel never establishes (PID stays `-`)

## When NOT to use

- General Vercel environment variable problems — use `vercel:env-vars` instead
- Railway or Docker runtime failures — use `curator-deployment` instead
- GitHub Actions failures unrelated to the four scenarios below

## Pipeline

### 1. dependency-review-action@v4 "not supported" error

**Cause:** `dependency-review-action@v4` requires the GitHub Dependency Graph to be enabled. Private repos also require GitHub Advanced Security (GHAS).

**Fix — choose one:**

Option A: Enable Dependency Graph in repo Settings → Code security → Dependency graph.

Option B: Gate the job so it skips on private repos without GHAS:

```yaml
jobs:
  dependency-review:
    if: github.event.repository.private == false
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/dependency-review-action@v4
```

Verify by re-running the workflow — the job must complete without the "not supported" message.

---

### 2. Stale Vercel rootDirectory after monorepo flatten

After removing `apps/web/` from a monorepo, the Vercel project still holds `rootDirectory: apps/web`. Builds succeed but deploy the wrong output or return 404 on all routes.

**Diagnose:**

```bash
vercel project inspect   # look for Root Directory field
```

**Fix:** Clear the field in the Vercel dashboard under Project → Settings → General → Root Directory (set to empty). Or via CLI:

```bash
vercel project set-root-directory ""
vercel deploy --prod
```

Verify the build log shows the repo root as the working directory at the top, not `apps/web`.

---

### 3. Branch protection required-status-check name drift

The GitHub UI shows all checks green, but merge is blocked because the branch protection rule references a check by an old name (renamed workflow or renamed job).

**Always run this before attempting merge:**

```bash
gh api repos/OWNER/REPO/branches/BRANCH/protection \
  --jq '.required_status_checks.contexts'
```

Cross-reference the output against the actual check names shown in the PR. On a mismatch, update the protection rule to match the current name:

```bash
gh api --method PATCH \
  repos/OWNER/REPO/branches/BRANCH/protection \
  --field required_status_checks.strict=true \
  --field "required_status_checks.contexts[]=correct-job-name"
```

Never bypass branch protection to work around a name mismatch — file a follow-up ticket and fix the rule instead.

---

### 4. macOS LaunchAgent plist for cloudflared tunnel

A plist that launches `cloudflared` without the full subcommand chain silently exits (with code 0) or logs "no such command" without surfacing as a LaunchAgent failure.

**Required ProgramArguments shape:**

```xml
<key>ProgramArguments</key>
<array>
  <string>/usr/local/bin/cloudflared</string>
  <string>tunnel</string>
  <string>run</string>
  <string>YOUR_TUNNEL_NAME_OR_UUID</string>
</array>
```

Do not omit `tunnel` and `run`. The bare `cloudflared` binary has no default subcommand.

**Load and verify:**

```bash
launchctl load ~/Library/LaunchAgents/com.cloudflared.tunnel.plist
launchctl list | grep cloudflared   # PID column must be non-zero
```

If PID is `-`, inspect the system log:

```bash
log show --predicate 'process == "cloudflared"' --last 5m
```

## Verification

After applying any fix, confirm with one concrete signal per scenario:

| Scenario | Pass signal |
|---|---|
| dependency-review | CI job completes with no "not supported" error |
| rootDirectory reset | Build log shows repo root as working dir; all routes resolve |
| branch protection | `gh pr merge` succeeds without bypass; protection contexts match actual job names |
| LaunchAgent cloudflared | `launchctl list` shows non-zero PID; tunnel endpoint responds to a probe request |
