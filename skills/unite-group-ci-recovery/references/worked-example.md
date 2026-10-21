> Moved from SKILL.md. Read when you want a worked example of applying this playbook to a small Synthex bug fix.

## 8 — Worked example: applying this skill to "fix a small bug in Synthex"

1. Open Linear, identify ticket (e.g. SYN-XXX)
2. Cut branch: `git checkout -b feature/agent-syn-xxx-short-desc`
3. Make changes
4. Run pre-flight checklist (§0)
5. Open PR with full metadata block (§1)
6. Watch CI via Monitor poll loop
7. If sandbox fails: check §2 for known patterns, fix it or document it with log evidence as a founder gate (§4 — never admin-merge)
8. If migration fails: §3 (run prereq detection + use MCP not CLI)
9. Once every check on the exact head is green, required or not, hand the PR to Phill to merge per `pr-release-gate` (branch deletion is his call too). A red check from step 7, optional or not, is still an open founder gate: report it with its evidence; it never counts as green
10. After Phill merges, update the Linear ticket to Done + drop a comment with the PR URL
