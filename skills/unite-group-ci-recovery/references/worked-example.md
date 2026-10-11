> Moved from SKILL.md. Read when you want a worked example of applying this playbook to a small Synthex bug fix.

## 8 — Worked example: applying this skill to "fix a small bug in Synthex"

1. Open Linear, identify ticket (e.g. SYN-XXX)
2. Cut branch: `git checkout -b feature/agent-syn-xxx-short-desc`
3. Make changes
4. Run pre-flight checklist (§0)
5. Open PR with full metadata block (§1)
6. Watch CI via Monitor poll loop
7. If sandbox fails: check §2 for known patterns, document + admin-merge if environmental
8. If migration fails: §3 (run prereq detection + use MCP not CLI)
9. Once green, squash-merge + delete branch
10. Update Linear ticket to Done + drop comment with the PR URL
