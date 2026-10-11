> Moved from SKILL.md. Read when a check shows skipping and you need to know whether that is intentional.

## 6 — Skipping checks reference

| Check | Repo where it lives | Why it skips | Fix |
|---|---|---|---|
| `validate-agent-metadata` | Synthex | Branch != `feature/agent-*` | Adopt convention (§1) |
| `run-quality-checks` | Synthex | Branch != `feature/agent-*` | Adopt convention (§1) |
| `security-scan` (lowercase, from agent-pr-checks) | Synthex | Branch != `feature/agent-*` | Adopt convention (§1). The Title-Case `Security Scan` from `security.yml` runs on all PRs — different check |
| `update-pr-status` | Synthex | Branch != `feature/agent-*` | Adopt convention (§1) |
| `Supabase Preview` | Synthex | No supabase/migrations diff for preview branch | Intentional — leave alone unless you're touching `supabase/migrations/*.sql` |
| `CodeQL` | Synthex | Path filter or push-only trigger | Intentional — leave alone |
| `Smoke test (prod)` | Pi-Dev-Ops | Only fires on push to main (not on PRs) | Intentional — leave alone |
