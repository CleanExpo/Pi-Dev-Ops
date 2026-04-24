## Summary

- Add `.gitleaks.toml` with 4 DigitalOcean credential detection rules (PAT `dop_v1_`, OAuth `doo_v1_`, Spaces access key, Spaces secret key) and portfolio-wide false-positive suppressions
- Add `docs/proposals/digitalocean-recon.md` documenting the full DO audit from session 7cb284e367f8

## Findings

| Finding | Repo | Severity | Action |
|---|---|---|---|
| `setup-digitalocean.sh:119` — token pattern match | DR-NRPG | HIGH | DR-734: manual verify + rotate if real |
| `VERCEL_DIGITALOCEAN_DEPLOYMENT.md:62` — DB connection string | DR-NRPG | HIGH | DR-734: manual verify + rotate if real |
| `*.ondigitalocean.app` DNS takeover risk | RestoreAssist | MEDIUM | Mitigated by dns_takeover_scan.yml (RA-1098) |
| Pi-Dev-Ops DO credential exposure | Pi-Dev-Ops | NONE | Clean — no DO tokens in source or git history |

## Test plan

- [ ] `python3 -c "content=open('.gitleaks.toml').read(); assert '[[rules]]' in content; assert 'digitalocean-pat' in content"` — TOML structure valid
- [ ] Confirm DR-734 filed in Linear (NRPG Operations Platform, Urgent)
- [ ] If gitleaks available: `gitleaks detect --source . --config .gitleaks.toml` on this repo — no self-matches

## Manual verification path

No interactive surface changed. This PR adds static config (`.gitleaks.toml`) and a docs file (`docs/proposals/digitalocean-recon.md`). Verification is reading the two new files and confirming DR-734 exists at https://linear.app/unite-group/issue/DR-734.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
