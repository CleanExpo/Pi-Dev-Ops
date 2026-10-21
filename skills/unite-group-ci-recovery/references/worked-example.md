> Moved from SKILL.md. Read when you want a worked example of applying this playbook to a small Synthex bug fix.

## 8 — Worked example: applying this skill to "fix a small bug in Synthex"

1. Open Linear, identify ticket (e.g. SYN-XXX)
2. Cut branch: `git checkout -b feature/agent-syn-xxx-short-desc`
3. Make changes
4. Run pre-flight checklist (§0)
5. Run `pr-release-gate`: independent review of the exact head, release receipt, then push the branch
6. Watch the branch CI via Monitor poll loop until GitHub has run that exact head green; only then open the PR as a draft with the full metadata block (§1)
7. If sandbox fails: check §2 for known patterns, fix it or document it with log evidence as a founder gate (§4 — never admin-merge)
8. If migration fails: §3 (run prereq detection + use MCP not CLI)
9. Once every applicable check on the exact head, required or not and including the PR-only checks, has passed, hand the draft PR to Phill to merge per `pr-release-gate` (branch deletion is his call too). A skip counts only if it is listed as intentional in [skipping-checks-reference.md](skipping-checks-reference.md) and at least one GitHub Actions check succeeded; name each skip in the handoff. A red check from step 7, optional or not, is still an open founder gate: report it with its evidence; it never counts as passed. A new commit restarts from step 5
10. After Phill merges, update the Linear ticket to Done + drop a comment with the PR URL
