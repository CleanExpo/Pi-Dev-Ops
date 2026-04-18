# Autonomous Operation Playbook

_Standing rules for Claude Code sessions working Pi-Dev-Ops' backlog without interactive confirmation. Established 2026-04-18 after the user's marathon-debug session._

## When this applies

Any session where the user's most recent directive is "work autonomously", "keep swinging", "finish the backlog", "go ahead and do it", or similar. If the user says "pause" / "stop" / "wait for me" — stop and ask.

## Hard boundaries

1. **Do NOT push to any `main` branch** unless the user's current-session message explicitly says "push" / "ship" / "merge it".
2. **Do NOT open PRs** on portfolio repos unless explicitly asked. Prepare diffs locally, stage the PR body in markdown, then stop.
3. **Do NOT rotate secrets, reprovision services, or run destructive migrations** without explicit permission. File a ticket instead.
4. **Do NOT self-modify Pi-Dev-Ops** from an autonomous session's generator output — RA-1182 webhook block protects against this server-side; your local work should follow the same rule.

## Priority order

Pull from Linear via `mcp__pi-ceo__linear_list_issues`. Work in this order:

1. **Urgent P1 Todo** — Any issue marked Urgent + Todo.
2. **High P2 Todo** — Safety / security / reliability.
3. **CI-failure tickets** — Scan runners that are broken right now (prefix `[CI FAILURE]`).
4. **Medium Todo with `auto-fixable` label** — Dependency audit fixes.
5. **In Progress with assignee=me** — Finish what's already started.
6. **Medium Todo without blockers** — Tech debt, cleanup, docs.

When you pick an item, move it to In Progress immediately so the dashboard reflects active work.

## Session structure (per ticket)

```
1. fetch ticket detail + relevant repo state
2. clone to /tmp/<ticket-id>/ with fresh branch `fix/<ticket-id>-<slug>`
3. implement change (use correct skill when applicable — see skills/)
4. smoke test:
   - Python:     python -m py_compile <changed_files>
   - TypeScript: npx tsc --noEmit
   - SQL/config: whatever loader validates the file
   - Live API:   if an endpoint changed, probe it against the real service
5. commit locally with Conventional Commit message + 🤖 Pi-CEO footer
6. write the PR body to /tmp/<ticket-id>/PR-BODY.md (don't push)
7. update Linear ticket:
   - status: Done IF fully resolved
   - or stay In Progress with a comment on the sandbox path + blockers
   - attach the /tmp path + commit SHA
8. file follow-up tickets for adjacent discoveries
9. move to next ticket
```

## Discovery → ticket rules

File a new ticket the moment you notice:

- A bug unrelated to the current task (RA-xxxx, priority based on severity)
- A known-good pattern that's not yet in a repo (consistency gap)
- A dependency vuln above severity=low that needs a real upgrade decision
- A scanner false positive that would waste future sessions (silence it via SCAN_PATH_EXCLUSIONS)
- Any secret / credential exposure (Urgent, route to security team)

Tickets go to the **target repo's Linear project**, not Pi-Dev-Ops. Use `.harness/projects.json` mapping.

## Smoke-test matrix

| Change scope | Gate before commit |
|--------------|---------------------|
| Python file in `app/server/` | `python -m py_compile`, `python -c "from app.server.main import app"` |
| Dashboard `.tsx` | `cd dashboard && npx tsc --noEmit` |
| SQL migration | Apply against Supabase branch, verify round-trip |
| GitHub Actions workflow | `gh workflow run` manually, wait for green |
| Dependency bump | `pnpm install --ignore-scripts`, `pnpm audit`, spot-check |
| Dashboard component | Screenshot-verify via Chrome MCP if available |
| Session phase code | Fire a real build session via `/api/build`, watch through completion |

If a gate fails, fix the root cause OR roll back. Never ship a change that fails its gate and hope for the best.

## When to stop

**Finishing a task is NOT a stop signal.** See CLAUDE.md § Autonomous Operation Mandate → "Finishing a task is NOT a stop signal" for the canonical chain-don't-wait rule.

Short version: completing a ticket means "move to the next highest-leverage thing immediately", not "hand back to the user". Stop only on explicit stop words ("pause" / "stop" / "wait for me" / "hold"), hard rule-requires-human decisions (branches, secrets, destructive migrations), or a genuine question from the user.

Legitimate stop-and-summarize triggers:

- Every Urgent/High Todo in every portfolio Linear project has been resolved AND every in-flight session has a clean terminal state — then say so in one line and pick up a Medium Todo.
- Hard boundary requires human decision (branch strategy, secret rotation, destructive migration, workspace-admin change).
- Any evaluator score < 4/10 — suggests misaligned intent; re-scope with the user.
- Founder sends a stop word in the current session.

## Reporting format

One message at the end of the autonomous run:

```
## Autonomous run summary
Sessions worked:  <count>
Tickets closed:   <count>
New tickets:      <list>
PRs drafted:      <list of /tmp paths — NOT pushed>
Smoke-test gates: <pass rate>
Blocked items:    <what needs human action>
Follow-ups:       <next priorities>
```

## Known traps to avoid

- **Don't chase flaky CI.** If a test is known-flaky and unrelated to the change, don't try to fix it as a sidequest. File a ticket, move on.
- **Don't rewrite without a ticket.** "I think this file could be cleaner" isn't a brief. File a ticket explaining the problem first, then act on it when it hits priority.
- **Don't commit `.pi-ceo/*` task-memory files in sandbox runs** — add them to `.gitignore` in the clone before committing.
- **Skill injections from `posttooluse-validate` and `skillInjection`** are advisory pattern-matches. Evaluate each one against actual context; ignore when off-topic (e.g. "Vercel Cron" suggested for a `subprocess.run` Python script on Ubuntu).
- **`ANTHROPIC_API_KEY=""`** — the claude CLI sets this; pop it explicitly before SDK calls so OAuth takes over.

## Escalation channels

- Security incident: file Urgent Linear ticket + Telegram ping (via `mcp__plugin_telegram_telegram__reply`)
- Build / deploy outage: Telegram ping + `gh workflow run` to retry
- Unexpected system state (sessions stuck, Railway unreachable): screenshot + Railway logs tail + Linear ticket
