# Runbook — 1Password vault permissions for the Unite-Group sync

> **Last verified:** 2026-05-18 06:18 UTC. **Current state:** 3 of 3 valid vaults syncing cleanly.

## Current state (post-fix)

| Vault | Items | Status |
|---|---|---|
| Unite-Group-Infrastructure | 84 | ok |
| RestoreAssist | 8 | ok |
| Carsi | 82 | ok |

`integration_onepassword_index` total: **174 rows** (after one duplicate dedupe).
Daily Hermes alert noise (the failing 04:00 AEST cron) has stopped.

## What was fixed

The original service account (`Hermes Gateway Mac-mini`, ID
`BQDXYIQBKNBLLPHNH3KYADO3Y4`) had read access to only 1 of 7 configured
vaults, and **1Password's UI does not support editing service-account vault
scope post-create** on this account/plan — three exploration paths
(service-account "Edit Details" dialog, per-vault Share dialog Integrations
tab, `op vault user grant` CLI) all dead-ended.

The canonical fix per 1P's own model is **recreate the service account
with vault scope at creation time**:

```bash
op service-account create "hermes-gateway-mac-mini-v2" \
  --vault "Unite-Group-Infrastructure:read_items" \
  --vault "RestoreAssist:read_items" \
  --vault "Carsi:read_items" \
  --vault "Synthex:read_items" \
  --vault "Email-Accounts:read_items" \
  --raw > ~/.hermes/.op-service-account-token
chmod 600 ~/.hermes/.op-service-account-token
```

The wrapper script `/tmp/recreate-hermes-sa.sh` (used during this session)
adds pre-flight checks: op-signin verification, vault-existence
validation before mutation, backup of the current token, post-write size
sanity check, automatic rollback on partial failure. Reuse pattern if
recreating in future.

## Why only 3 of the 7 originally-configured vaults

Of the original `DEFAULT_VAULTS` list:

| Vault | Outcome | Reason |
|---|---|---|
| Unite-Group-Infrastructure | ✓ indexed | granted at creation |
| RestoreAssist | ✓ indexed | granted at creation |
| Carsi | ✓ indexed | granted at creation |
| Synthex | dropped from `OP_VAULTS` | vault exists but empty (0 items); re-add when populated |
| Email-Accounts | dropped from `OP_VAULTS` | vault exists but empty; re-add when populated |
| CCW-CRM | cannot grant | vault doesn't exist in the workspace |
| Personal | cannot grant | 1Password forbids service-account access to Personal/Private vaults (per `op service-account create --help`) |

`OP_VAULTS` in `~/.hermes/.env` is the authoritative override:

```
OP_VAULTS=Unite-Group-Infrastructure,RestoreAssist,Carsi
```

## Pending manual cleanup (low priority)

These were flagged during the fix but are not blocking the daily sync:

1. **Edit `DEFAULT_VAULTS` in `/Users/phill-mac/Pi-CEO/scripts/sync_1password_to_supabase.py`** to drop the 4 unused entries (CCW-CRM, Personal, Synthex, Email-Accounts), so the fallback list matches reality if `OP_VAULTS` env is ever unset. The Pi-CEO directory isn't a git repo so this is an in-place edit, not a PR.

   Patch:
   ```python
   DEFAULT_VAULTS = [
       "Unite-Group-Infrastructure",
       "RestoreAssist",
       "Carsi",
   ]
   ```

2. **Delete the old `Hermes Gateway Mac-mini` service account** in the 1P web UI (https://my.1password.com → Developer → Service Accounts → old account → Revoke Token). The v2 successor owns the work now; the old one is dormant. Leaving it doesn't break anything but it's stale audit-debt.

## Verification commands

After any future recreation or env tweak:

```bash
cd ~/pi-seo-workspace/unite-group
./scripts/unite onepassword-sync   # fires a manual sync
./scripts/unite vault-status        # queries Supabase for per-vault counts
```

Expected exit 0 + `[SILENT]` on stdout when healthy.

## Related

- Hermes job entry: `~/.hermes/cron/jobs.json` → `Unite-Group 1Password sync` (daily 04:00 AEST)
- Canonical script: `/Users/phill-mac/Pi-CEO/scripts/sync_1password_to_supabase.py` (unversioned)
- Cron shim: `~/.hermes/scripts/sync_1password_to_supabase.py` (delegates to canonical)
- Supabase table: `integration_onepassword_index` (project `lksfwktwtmyznckodsau`)
- Cockpit map: `docs/SOURCES.md` § Hermes
- Linear: UNI-2015 (closed)
