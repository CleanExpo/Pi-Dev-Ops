---
name: vercel-env-puller
description: Per-project Vercel env-var manifests (NAMES + targets only — never values). At Sandcastle launch time, resolves the named vars in-memory via `vercel env pull`, injects into the sandbox via Sandcastle's `agent.env`+`sandbox.env`, and never writes a secret to disk inside Pi-CEO. Closes Wave 5 #2 (RA-1856 epic).
owner_role: CISO (binds in front of every Sandcastle launch)
status: wave-5
---

# vercel-env-puller

The hardest part of Wave 5. AFK Sandcastle agents need real production secrets to call real DBs / real Anthropic / real Stripe. The manifest design enforces four invariants so secrets never accumulate where they can leak.

## Why this exists

The Wave 5 recon (Phase 1, this session) found 80+ unique env vars across 9 portfolio projects. Naive injection would let a single Sandcastle run see every secret in `process.env`. That violates least-privilege and creates a single exfiltration path.

This skill enforces:

1. **Pi-CEO must not log secrets** — manifests store names only; stdout from Sandcastle is regex-stripped before reaching `session.logs`.
2. **Pi-CEO must not write secrets to disk** — Sandcastle config file lives on tmpfs (Linux `/dev/shm`) or named pipe (macOS `mkfifo`); always unlinked in `finally`.
3. **ANTHROPIC_API_KEY rotation must not silently break 7 projects** — auth-failure pattern detection emits `cfo_alert`; manifest `criticality:blocker` flag triggers escalation lock.
4. **Per-project secrets must not leak across project sandboxes** — each Sandcastle run receives ONLY the resolved env dict for the target repo.

## Manifest format

`Pi-Dev-Ops/.harness/env-manifests/{project-slug}.json`:

```json
{
  "version": "1.0",
  "generated_at": "2026-05-02T07:30:00Z",
  "vercel_team": "unite-group",
  "vercel_project_id": "prj_AbCdEf123",
  "project_slug": "restoreassist",
  "vars": [
    {
      "name": "ANTHROPIC_API_KEY",
      "target": "production",
      "category": "ai-provider",
      "criticality": "blocker"
    },
    {
      "name": "DATABASE_URL",
      "target": "production",
      "category": "database",
      "criticality": "blocker"
    },
    {
      "name": "STRIPE_SECRET_KEY",
      "target": "production",
      "category": "payments",
      "criticality": "blocker"
    },
    {
      "name": "NEXT_PUBLIC_SUPABASE_URL",
      "target": "production",
      "category": "client-public",
      "criticality": "skip"
    }
  ],
  "skipped": [
    "DASHBOARD_PASSWORD",
    "TAO_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PLAUSIBLE_*",
    "POSTHOG_*",
    "NEXT_PUBLIC_*"
  ]
}
```

### Field semantics

| Field | Allowed values | Effect |
|---|---|---|
| `category` | `ai-provider`, `database`, `payments`, `observability`, `analytics`, `client-public`, `dashboard-only`, `telegram-only`, `unknown` | Drives default skipped behaviour + auth-failure routing |
| `criticality` | `blocker`, `degraded`, `optional`, `skip` | `blocker` failure → halt all in-flight runs; `degraded` → continue + alert; `optional` → silent fallback; `skip` → never injected |
| `target` | `production`, `preview`, `development` | Which Vercel target to pull from. Default `production` for autonomy runs. |

## Least-privilege filter (hardwired)

Always skip — even if absent from `skipped[]`:

| Pattern | Why |
|---|---|
| `NEXT_PUBLIC_*` | Client-side; not secrets but bloat |
| `DASHBOARD_PASSWORD`, `TAO_PASSWORD` | Pi-CEO operator auth, irrelevant to portfolio repos |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Pi-CEO ops channel; not for portfolio code |
| `PLAUSIBLE_*`, `POSTHOG_*` | Analytics; portfolio code doesn't need them |
| `VERCEL_TOKEN`, `VERCEL_GIT_*` | Vercel-build-environment-only |
| `*_DEPLOY_HOOK_*` | Build-trigger auth; don't expose to runtime |

## Refresh mechanism (no values stored, ever)

A scheduled task runs monthly per project:

```bash
cd /tmp/manifest-refresh-{project_slug}
vercel pull  # links project — no values yet
vercel env ls --json --environment=production > /tmp/raw.json
python3 scripts/refresh_env_manifest.py \
  --slug {project_slug} \
  --raw /tmp/raw.json \
  --out .harness/env-manifests/{project_slug}.json
rm /tmp/raw.json
```

`scripts/refresh_env_manifest.py` (Wave 5 #2 deliverable):
1. Reads raw `vercel env ls --json` output (which contains only names, types, targets, NOT values).
2. Diffs against existing manifest — flags new names, removed names.
3. Auto-classifies category from name pattern (e.g. `*_API_KEY` → `ai-provider` if matches a provider list, else `unknown`).
4. Preserves `skipped[]` array verbatim (operator-curated; refresh never auto-edits).
5. New names default to `criticality: "unknown"` until operator reviews via PR.

Manifest changes ship through normal git review. Values never enter the diff because `vercel env ls --json` doesn't return values.

## Runtime injection — the security boundary

This is the hot path called by `sandcastle-runner` at launch time:

```python
def resolve_for_run(*, project_slug: str, run_id: str) -> tuple[dict[str, str], str]:
    """
    Returns (env_dict, config_file_path).
    The dict contains ACTUAL VALUES — caller must never log it, never persist it.
    The config file path is on tmpfs and MUST be unlinked by caller in finally.
    """
    # 1. Load manifest (names only)
    manifest = _load_manifest(project_slug)
    
    # 2. Filter against hardwired skipped[] + manifest.skipped[]
    needed_names = [v["name"] for v in manifest["vars"]
                    if v["criticality"] != "skip"
                    and not _matches_skip_patterns(v["name"])]
    
    # 3. Pull values via `vercel env pull` to a TMPFS pipe (NOT a file in /tmp)
    if sys.platform == "linux":
        # /dev/shm is RAM-backed tmpfs by default
        pull_path = f"/dev/shm/sandcastle-pull-{run_id}.tmp"
    else:
        # macOS doesn't have /dev/shm; use mkfifo
        pull_path = f"/tmp/sandcastle-pull-{run_id}.fifo"
        os.mkfifo(pull_path, mode=0o600)
    
    try:
        # vercel env pull writes a `.env`-format file at the path
        subprocess.run(
            ["vercel", "env", "pull", pull_path,
             "--environment=production",
             "--scope", "unite-group",
             "--yes"],
            check=True, capture_output=True
        )
        
        # Parse in-memory; immediately unlink the pull file
        all_env = _parse_dotenv(pull_path)
    finally:
        if os.path.exists(pull_path):
            os.unlink(pull_path)
    
    # 4. Filter to only needed names (defense in depth)
    filtered = {k: v for k, v in all_env.items() if k in needed_names}
    
    # 5. Write Sandcastle config to a separate tmpfs file
    config_path = f"/dev/shm/sandcastle-config-{run_id}.json" \
                  if sys.platform == "linux" \
                  else f"/tmp/sandcastle-config-{run_id}.json"
    
    config = {
        "agent": {"name": "claudeCode", "env": filtered},
        "sandbox": {"name": "docker"},
        # ... rest of Sandcastle config
    }
    
    with open(config_path, "w") as f:
        os.chmod(config_path, 0o600)
        json.dump(config, f)
    
    # 6. Audit emit — NAMES ONLY, never values
    audit_emit.row(
        "sandcastle_env_resolved",
        actor_role="Builder",
        run_id=run_id,
        project_slug=project_slug,
        var_count=len(filtered),
        var_names=list(filtered.keys()),  # names safe to log
    )
    
    return filtered, config_path
```

**Caller MUST:**
- Treat `filtered` as ephemeral; don't pass it to anything except the Sandcastle subprocess.
- Unlink `config_path` in a `finally` block, no matter what.
- Never `print()`, `log.info()`, or `audit_emit.row(..., env=filtered)` the dict.

## Auth-failure detection (CFO-bot integration)

After every Sandcastle run, the runner inspects `log_tail` for these patterns:

```
401 Unauthorized
403 Forbidden
Invalid API key
Authentication failed
authentication_error
permission_denied
```

If found AND the run consumed any var with `criticality: "blocker"`:

1. `audit_emit.row("cfo_alert", ..., alert_type="env_var_auth_failed", project_slug=..., var_name=NAME)` — name only, never value.
2. `draft_review.post_draft(draft_text=f"🚨 Auth failure on {project_slug}: {var_name} likely rotated", drafted_by_role="CFO", ...)` — Telegram alert.
3. Set in-memory escalation lock: no new Sandcastle runs against that project until manifest review.

The lock auto-expires after 1 hour OR when the operator manually clears it via Telegram `/sandcastle clear-lock {project_slug}`.

## Per-project isolation

Each Sandcastle run gets exactly ONE manifest. The runner:
- Loads `{project_slug}.json` based on `repo_workdir` mapped via `.harness/projects.json`.
- Never reads any other manifest.
- Validates against Sandcastle's own `agent.env`+`sandbox.env` non-overlap rule before launch.
- Uses Sandcastle's `cwd` parameter to prevent the agent from `cd`-ing into another project's worktree.

## Initial bootstrap manifests (Wave 5 #2 ships)

Per the recon — 9 projects to seed. Phase A ships these 9 manifests:

| project_slug | source repo | manifest priority |
|---|---|---|
| restoreassist | CleanExpo/RestoreAssist | High — already debugging Cloudinary + Xero today |
| pi-dev-ops | CleanExpo/Pi-Dev-Ops | High — Pi-CEO eats own dogfood |
| synthex | CleanExpo/Synthex | High — has Stripe + Anthropic |
| ccw-crm | CleanExpo/CCW-CRM | Medium |
| disaster-recovery | CleanExpo/DR-Sandbox | Medium |
| dr-nrpg | CleanExpo/DR-NRPG | Medium |
| nrpg-onboarding | CleanExpo/NRPG-Onboarding-Framework | Low |
| carsi | CleanExpo/CARSI | Low |
| unite-group | CleanExpo/Unite-Group | Low |

Initial seed: run `vercel env ls --json --environment=production` for each, classify auto, commit manifest, operator reviews PR before merge.

## Verification (Wave 5 #2 close-out)

1. **Manifest schema lint** — every manifest validates against `.harness/env-manifests/manifest.schema.json`.
2. **Refresh dry-run** — run `scripts/refresh_env_manifest.py --slug pi-dev-ops --dry-run`, verify diff output names new vars without values.
3. **Resolve smoke** — call `resolve_for_run(project_slug="pi-dev-ops", run_id="smoke-1")` → returned dict has the expected names; config file exists at `/dev/shm/sandcastle-config-smoke-1.json` (mode 0600); after `os.unlink`, file gone; `audit_emit` row written with `var_names` array but NO values.
4. **Skip-pattern enforcement** — synthetic manifest with `NEXT_PUBLIC_TEST_KEY` → resolve filters it out; not in returned dict.
5. **Cross-project isolation** — call `resolve_for_run(project_slug="restoreassist")` then `resolve_for_run(project_slug="synthex")` in the same Pi-CEO process → returned dicts share no overlapping non-public keys (tested by intersection).
6. **Auth-failure escalation simulation** — feed a synthetic Sandcastle log_tail containing `401 Unauthorized` → verify `cfo_alert` audit row + draft posted via draft_review (TEST_MODE) within 60 s.
7. **Secret-leak grep over all artefacts**:
   ```
   grep -RE '(?:[A-Z_]{4,}_(?:KEY|TOKEN|SECRET|PASSWORD))[^A-Z_]+[A-Za-z0-9/+=]{16,}' \
     .harness/swarm/swarm.jsonl \
     .harness/env-manifests/ \
     /tmp/pi-ceo-workspaces/sandcastle/
   ```
   → must return ZERO matches across 10 consecutive smoke runs.

## Out of scope for Wave 5 #2

- Vault integration (Hashicorp / 1Password / AWS Secrets Manager) — Vercel is the source of truth; we don't reinvent vaulting.
- Cross-team manifest sharing — each manifest is project-local.
- Manifest hot-reload — refresh is monthly + on-demand; no in-process file-watcher.
- Encrypting manifests at rest — they contain no values; encryption is over-engineering.

## References

- Vercel CLI docs: `vercel env ls --json`, `vercel env pull`
- Sandcastle env resolution: `~/.cache/sandcastle/EnvResolver.ts` (in node_modules)
- Approved plan: `/Users/phill-mac/.claude/plans/breezy-wiggling-map.md`
- Companion skill: `sandcastle-runner` (consumer)
- Existing audit substrate: `swarm/audit_emit.py`
- Existing CFO bot (Wave 4.1, RA-1850 — DONE): `swarm/cfo.py` + `swarm/bots/cfo.py`
- Parent epic: <issue id="RA-1856">RA-1856</issue>
