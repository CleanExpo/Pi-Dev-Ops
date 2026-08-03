# /sync-skills

Safely scan and promote specialised skills into the Pi-Dev-Ops canonical library.

Usage:

```bash
scripts/sync-skills scan
scripts/sync-skills apply .harness/skill-sync/reports/SKILL-SYNC-YYYY-MM-DD.md
```

Rules:

- `scan` is read-only and writes a dated report under `.harness/skill-sync/reports/`.
- `apply` promotes only report rows explicitly checked as `APPROVE_PROMOTE`.
- Same-name conflicts are never resolved automatically.
- Existing real directories under `~/.claude/skills/` are reported and left untouched.
