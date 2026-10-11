> Moved from SKILL.md. Read when you are about to admin-merge a failing check and should spawn an investigator agent first.

### How to use this skill agentically (added 2026-05-25)

The skill is not a label to slap on a PR comment — it's a callable procedure. Before admin-merging any failing check, spawn an investigator agent with this prompt template:

```
You are applying the unite-group-ci-recovery skill at
/Users/phillmcgurk/Pi-CEO/skills/unite-group-ci-recovery/SKILL.md.

Read it end-to-end, then for the failure at <PR URL>:
1. Use Vercel MCP get_project + list_deployments + get_deployment_build_logs
   to determine the actual root cause (with log evidence)
2. Determine which class from §2 (JWT_SECRET / OOM / rootDirectory / framework=null / etc)
3. Count consecutive failures on the same project — apply §4 STOP rule if ≥5
4. Report: (a) fixable now via MCP, (b) fixable in <5 min by user UI work,
   (c) needs escalation per STOP rule, (d) truly waits on backlog.

Do not cite any Linear ticket unless you've confirmed the ticket's failure mode
matches the current failure mode exactly.
```

This prevents the parent agent from reflexively pattern-matching "sandbox red → DR-852 → admin-merge".
