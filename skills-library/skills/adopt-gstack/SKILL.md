---
name: adopt-gstack
description: How gstack (garrytan/gstack) is installed and used in this estate — which gstack-* skill to reach for, what it must never do here, and how to move the pin. Use when choosing between a gstack-* skill and an estate skill, when a gstack skill is missing on a machine, or before bumping the gstack version.
---

# gstack in this estate

gstack is Garry Tan's role-based skill suite (office hours, CEO/design plan review, QA in a
real browser, review, ship, retro) plus a persistent headless browser (`browse`, ~100-200 ms
per command after a ~3 s first start). It is installed at ONE pinned commit, curated, for
Claude Code and Codex. Source: `~/Developer/gstack-pinned`. Installer: `install/install-gstack.sh`.
The source checkout is **installer-owned**: never edit files there. Every install discards its
working-tree edits (upstream `./setup --prefix` rewrites tracked files each run) and refuses only
if it holds local commits that are not on origin.

## When to use which (estate skill wins where it already covers the role)

| Need | Use | Not |
|---|---|---|
| QA a live site and fix what breaks | `gstack-qa` (report only: `gstack-qa-only`) | — (gap we did not cover) |
| Page speed / regression | `gstack-benchmark`, post-deploy `gstack-canary` | — |
| Stop destructive commands / lock edits to a dir | `gstack-careful`, `gstack-freeze`, `gstack-guard` | — |
| Save / resume a long session | `gstack-context-save` / `gstack-context-restore`, then `session-handoff` | — |
| Docs after a release | `gstack-document-release` | — |
| Weekly retro from git history | `gstack-retro` | — |
| Sharpen an idea / scope a plan | `gstack-office-hours` → `gstack-plan-ceo-review` | before `/spm` |
| Design plan / live visual QA | `gstack-plan-design-review`, `gstack-design-review` | after `mobbin-ui-patterns` |
| Security audit / code health score | `gstack-cso`, `gstack-health` | — |
| Architecture / eng plan review | `engineering-requirements` | gstack plan-eng-review (not installed) |
| Diff review | `opus-adversary` + cross-vendor lane; `gstack-review` as an extra lane only | never the only lane |
| Debug | `superpowers:systematic-debugging` or `gstack-investigate` | — |
| Open a PR | `gstack-ship` is fine — the `pr-release-gate` hook still fires on push / `gh pr create` | never bypass the gate |
| Merge / deploy | UG-AUTONOMY-001 or Phill | `land-and-deploy` (deliberately not installed) |

Browser choice: gstack `browse` for headless QA runs and scripted flows; claude-in-chrome for
Phill's own logged-in Chrome. gstack's README line "never use claude-in-chrome" is NOT adopted.

## Hard limits

- `~/.claude/settings.json` must never gain a gstack hook. The installer runs setup with
  `--no-timeline-stop-hook --no-plan-tune-hooks` and fails if settings.json changes.
- Telemetry off, `auto_upgrade: false`, `proactive: false` (`~/.gstack/config.yaml`).
- `gstack-upgrade` and `setup-browser-cookies` are not installed: upgrades move only by pin,
  and browser cookies are credentials (see `credential-custody`).
- On RestoreAssist, `gstack-qa` commits fixes: Tier 1 surfaces (auth, tenancy, billing,
  migrations) still need the full independent review before push.

## Check / repair on any machine

```
bash ~/.claude/skills/adopt-gstack/install/install-gstack.sh --check   # verify
bash ~/.claude/skills/adopt-gstack/install/install-gstack.sh           # install / repair
```

`bootstrap.sh` runs the installer, so `git -C ~/.claude pull && bash ~/.claude/bootstrap.sh`
brings a new machine level. The `gstack-*` links are machine-local and gitignored.

## Moving the pin

1. Read the upstream CHANGELOG from the current pin to the candidate commit.
2. Re-run the throwaway-HOME proof: `HOME=<tmp> ./setup --host claude --prefix --no-team
   --no-plan-tune-hooks --no-timeline-stop-hook`, then confirm `<tmp>/.claude/settings.json`
   is unchanged and new skills are only prefixed `gstack-*`.
3. Update `PIN` in `install/install-gstack.sh`, review `allowlist.txt`, then PR through
   `pr-release-gate`.
