# Pi-CEO Strategic Intent (Founder Mandate — 2026-04-19)

Every session reads this file via `brief.py` as "STRATEGIC INTENT" context.
The planner and orchestrator MUST honour these standards before generating any code.

## Quality Mandate — 100% Clean Across All Surfaces

The founder's exact directive (2026-04-19): *"clean data, code 100%, Security 100%,
Research 100%, Development 100%."*

| Surface | Definition of 100% Clean | How the planner enforces it |
|---------|--------------------------|-----------------------------|
| **Data** | No orphan rows, no dupes, schemas validated, migrations reversible, backups verified | Before any schema/data change, planner drafts validation queries and rollback script |
| **Code** | All tests pass, strict types, no warnings, no dead code, function < 40 lines, file < 300 lines | Evaluator rejects diffs that add `any`, `# type: ignore`, unused imports, or silent fallbacks |
| **Security** | bcrypt passwords, HMAC-verified webhooks, parameterised queries, CSP headers, no secrets in code, dependency scan clean | detect-secrets + Pi-SEO gates must pass; `sk-*`/`lin_api_*`/`ops_*` in diff = hard reject |
| **Research** | Latest official docs cited (Anthropic, Linear, Vercel, Supabase), ≥ 2 authoritative sources for any API usage, competitor/alternative explicitly considered | Every planner spec must link to ≥ 1 live doc URL; no "I think this is how X works" |
| **Development** | PRs small (< 400 LOC), branch clean, commits conventional, ship phase verified end-to-end per RA-1109, Linear ticket updated on every transition | Ship gate hard-fails if manual-verification-path is empty |

## Agent Hierarchy — Every Build Flows Through Seniors

```
Senior PM (planner, Opus 4.7)
      │
      ▼
Senior Orchestrator (orchestrator, Opus 4.7)
      │
      ├─► Research Sub-agents (Sonnet + Haiku)
      │     • scout         — external intel (GitHub, ArXiv, HN)
      │     • intel-refresh — Anthropic docs + Linear product updates
      │     • plan-discovery — 3 variant plans scored, best wins
      │     • perplexity_research MCP — live web facts + citations
      │
      ▼
Generator (Sonnet 4.6)   ◄─── receives enriched plan + research brief
      │
      ▼
Evaluator (Sonnet 4.6)   ◄─── scores against 100%-clean criteria, threshold 8.5+
      │
      ▼
Board (Sonnet 4.6, daily 05:00 UTC)  — reviews yesterday's merged work,
                                        flags any regression of the 100% standard
```

Opus 4.7 is reserved for planner + orchestrator only (RA-1099). Widening this
violates budget policy. If a non-senior role needs opus-level thinking, route
the specific sub-question BACK through the planner instead of escalating the
generator.

## Research Sub-Agents Fire Constantly (Founder directive 2026-04-19)

The research agents MUST be considered under-utilised unless they fire at the
following minimum cadence:

| Agent | Minimum cadence | Consumes |
|-------|-----------------|----------|
| scout | twice daily (04:30 + 16:30 UTC) | GitHub + ArXiv + HN search; creates scout-labelled Linear tickets for the board |
| intel-refresh | daily 02:00 UTC | Re-fetches Anthropic release notes + API docs, writes to `.harness/anthropic-docs/` |
| feedback-loop | daily 12:00 UTC | Analyses last 24 h session outcomes (success/failure/retry patterns), surfaces to evaluator |
| plan-discovery | every generator session (always-on) | 3 variant plans scored via haiku, best prepended to spec |
| board-meeting | daily 05:00 UTC | Strategic review, publishes minutes to `.harness/board-meetings/` |

A planner SHOULD explicitly note which research documents informed their plan.
Plans without cited research are flagged by the evaluator.

## Backlog-Sweep Objectives (active 2026-04-19 onward)

- **Drain Urgent+High first** — poll interval 30 min, 1 session at a time, 60-min budget (tier 3, sonnet, eval threshold 9.0, 3 retries)
- **Route every ticket through spec → plan → test → ship** — no shortcuts
- **Every ship attempt updates Linear** with a manual-verification-path comment
- **Surface-treatment prohibition (RA-1109)** — HTTP 200 is not "shipped". Ship gate requires a click-test URL OR a specific log line proving the user-visible outcome
- **Repo routing** — `.harness/projects.json` maps ticket → target repo → Linear team/project. Tickets without routing are flagged back to the board, not guessed at

## Cost Discipline (active 2026-04-19)

- Anthropic: Max 20x OAuth only (`sk-ant-oat01-*`). Paid API key (`sk-ant-api03-*`) is a **regression** and triggers immediate rollback.
- Railway compute: max 1 concurrent session by default. Widen to 2–3 only after a clean 72-hour run at 1 with no overage.
- Orphan projects, stale branches, failed-CI PRs waste compute. Board meeting reviews weekly; evaluator flags on sight.

## Change-Log Convention

Every material change to this document goes to `.harness/intent/RESEARCH_INTENT.md.log`
(append-only). Agents writing here must include:

```
<ISO8601> <agent> <one-line reason> <diff-link>
```

The pattern-analyser in `plan_discovery.py` proposes updates to this file
automatically after every 50 session discoveries.
