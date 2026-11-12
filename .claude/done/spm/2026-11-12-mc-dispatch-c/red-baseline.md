# Red baselines, before any fix

Worktree HEAD 1b2bcd966de8f6869742598c89d37cb252340acb (origin/main), no code changes, 2026-11-12 ~13:20 AEST.
Mini `~/.ssh/config` unchanged at this point.

## C7 `fleet_probe_resolves.sh` — exit 1

```
macbook reachable=False error=ssh: Could not resolve hostname macbook-ts: nodename nor servname provided, or not known
windows reachable=False error=ssh: Could not resolve hostname win-ts: nodename nor servname provided, or not known
exit=1
```

## C6 `fresh_process_proof.sh` (contract w_6e6e1ff459e0 version) — exit 1

```
fleet_status state=unknown reason=mission-control not configured: MC_LANE_URL / MC_LANE_SECRET unset machines=[]
exit=1
```

So the old mod, loaded from this worktree into a Claude Code process with no MC_LANE_* in its environment,
reports unconfigured even though launchd holds both values. This is the desktop app's state after a reboot.
