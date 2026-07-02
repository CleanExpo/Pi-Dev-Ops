## Summary

- Repoint all operational Pi-Dev-Ops references from `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops` to `/Users/phill-mac/Pi-Dev-Ops` (canonical workspace).
- Hermes global config (`~/.hermes/config.yaml`) and empire profile (`~/.hermes/profiles/empire/config.yaml`) `mcp_servers.pi-ceo` now resolve `pi-ceo-server.js` and `HARNESS_DIR` from the new path — Margot's `margot_turn` / `margot_voice_turn` bridge routes through this MCP server.
- LaunchAgent routines worktree left at existing `~/Pi-CEO/Pi-Dev-Ops-routines` (still valid); `install.sh` REPO updated to canonical path for future worktree creation.

## Hermes update (local, not in this PR)

| Stage | SHA |
|-------|-----|
| Before pull | `41c85fb9469bbde7c5446cc5386b2e2438936fb5` |
| After `git pull` | `a4a562ff0` (tag `v2026.7.1`, 632 commits) |
| After `hermes update` | `019950560d43f1058d0966b95480d73ed8daf034` |

Notable upstream changes: config format v31→v33, per-channel model/prompt overrides, Camofox private-page SSRF guard, cua-driver 0.7.0, gateway stale-timeout fixes.

## Test plan

- [x] `hermes mcp list` — `pi-ceo` enabled, path shows `/Users/phill-mac/Pi-Dev-Ops/mcp/...`
- [x] `hermes skills list` — empire profile skills load
- [x] `curl http://127.0.0.1:8642/health` → 200 after gateway kickstart
- [ ] Send Margot a Telegram text message — confirm `mcp__pi-ceo__margot_turn` fires and reply returns
- [ ] Optional: voice note → `mcp__pi-ceo__margot_voice_turn`
- [ ] `bash scripts/install_skills.sh --dry-run` — symlinks target `/Users/phill-mac/Pi-Dev-Ops/skills/`
- [ ] Re-run `scripts/launchagents/install.sh` when ready to migrate routines worktree off `~/Pi-CEO/Pi-Dev-Ops-routines`

## Follow-ups for Phill

1. **Routines worktree migration** — canonical repo is `/Users/phill-mac/Pi-Dev-Ops` but LaunchAgent plists still run scripts from `~/Pi-CEO/Pi-Dev-Ops-routines`. Create a detached/routines branch worktree when ready: `git -C /Users/phill-mac/Pi-Dev-Ops worktree add -b routines-main ~/Pi-Dev-Ops-routines main`, then update plists.
2. **Gmail MCP** — `mcp_servers.gmail` still has `FILL_IN` OAuth placeholders (disabled); not blocking Margot.
3. **Historical docs** — `docs/superpowers/plans/*` still reference `~/Pi-CEO/Pi-Dev-Ops` in archived plan text; operational scripts/skills updated.
