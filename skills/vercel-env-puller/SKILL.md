---
name: vercel-env-puller
description: "Per-project Vercel env-var manifests (NAMES + targets only, never values). At Sandcastle launch, resolves the named vars in-memory via `vercel env pull` and injects them through Sandcastle's `agent.env` + `sandbox.env`; never writes a secret to disk inside Pi-CEO. Use when an AI agent must supply production secrets to an AFK Sandcastle run, or when creating, refreshing or reviewing manifests under `.harness/env-manifests/{project-slug}.json` (var names, targets, categories, criticality: blocker, degraded, optional, skip)."
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

Read references/manifest-format.md when creating, editing or reviewing a manifest under .harness/env-manifests/.

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

This is the hot path called by `sandcastle-runner` at launch time.

**The agent env and the sandbox env must be disjoint.** `sandcastle_run.mts` passes them to `run()` as `agentEnv` (into `claudeCode({ env })`) and `sandboxEnv` (into the sandbox provider's `env`). `run()` in @ai-hero/sandcastle@0.12.0 throws `Overlapping env keys between agent provider and sandbox provider: <KEYS>` if any key appears in both, so assign every manifest var to exactly one side.

```python
def resolve_for_run(*, project_slug: str, run_id: str, cwd: str, model: str,
                    branch: str, prompt: str) -> tuple[dict[str, str], str]:
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
    
    # Shape read by scripts/sandcastle_run.mts (see sandcastle-runner SKILL.md).
    config = {
        "cwd": cwd,
        "model": model,
        "branch": branch,            # named job branch, never the host's current one
        "prompt": prompt,
        "sandbox": "docker",
        "agentEnv": filtered,        # every manifest var on exactly one side
        "sandboxEnv": {},
        "killSwitchFiles": [".harness/swarm/kill_switch.flag"],
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

Read references/auth-failure-detection.md when wiring or debugging auth-failure detection and the cfo_alert escalation.

## Per-project isolation

Each Sandcastle run gets exactly ONE manifest. The runner:
- Loads `{project_slug}.json` based on `repo_workdir` mapped via `config/harness/projects.json`.
- Never reads any other manifest.
- Validates against Sandcastle's own `agent.env`+`sandbox.env` non-overlap rule before launch.
- Uses Sandcastle's `cwd` parameter to prevent the agent from `cd`-ing into another project's worktree.

## Initial bootstrap manifests (Wave 5 #2 ships)

Read references/bootstrap-manifests.md when seeding or refreshing the initial per-project manifests.

## Verification (Wave 5 #2 close-out)

Read references/verification.md when closing out or re-verifying the env-puller implementation.

## Out of scope for Wave 5 #2

- Vault integration (Hashicorp / 1Password / AWS Secrets Manager) — Vercel is the source of truth; we don't reinvent vaulting.
- Cross-team manifest sharing — each manifest is project-local.
- Manifest hot-reload — refresh is monthly + on-demand; no in-process file-watcher.
- Encrypting manifests at rest — they contain no values; encryption is over-engineering.

## References

- Vercel CLI docs: `vercel env ls --json`, `vercel env pull`
- Sandcastle env resolution: `~/.cache/sandcastle/EnvResolver.ts` (in node_modules)
- Approved plan: `~/.claude/plans/breezy-wiggling-map.md`
- Companion skill: `sandcastle-runner` (consumer)
- Existing audit substrate: `swarm/audit_emit.py`
- Existing CFO bot (Wave 4.1, RA-1850 — DONE): `swarm/cfo.py` + `swarm/bots/cfo.py`
- Parent epic: <issue id="RA-1856">RA-1856</issue>
