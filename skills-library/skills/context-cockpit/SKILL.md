---
name: context-cockpit
description: Audit and reclaim a session's context/token budget in one pass — read /context, trim MCP tools, clear vs compact, CLI-over-MCP, model ladder, red-MCP triage.
argument-hint: "[optional: what you're about to do, so the reclaim targets it]"
disable-model-invocation: true
allowed-tools: Read, Bash
---

# context-cockpit — inspect the window, then reclaim it

One pass to answer "why is this session heavy, and what do I run next." A thin orchestrator
over Claude Code's native context tools — it reads `/context` and hands you the exact next
move; it does not replace it. Absorbs MCP triage (the former `mcp-doctor`). Which substrate
to reach for belongs to `connector-routing`; this triages what a session already loaded.

## Step 1 — Read the window (`/context`)
Run `/context`. It lists every loaded item — system prompt, MCP tool lists, files read,
message history — with token counts and % of window. Rank the top 3 token-eaters and mark
each keep / trim / drop against what the task at hand (the argument) actually needs.
- Fuel-gauge thresholds: **<50%** build freely · **50–70%** getting heavy, wrap or compact ·
  **>85%** danger — quality already slipped, don't start real work here.
- **Completion criterion:** top-3 eaters named, each with a keep/trim/drop verdict.

## Step 2 — Trim MCP tools under 50
Every connected MCP loads its FULL tool list at startup, used or not — three servers can eat
~66% of the window before any work begins. Target **enabled tool count < 50** and **3–5
servers max** (past that, tool-selection accuracy drops, not just tokens).
```bash
claude mcp list        # what's connected and taxing you
```
Also run `/mcp` for the in-session per-server token cost. Disconnect anything not used THIS
session (rule: "every session? no → disconnect until you do"). A heavy-but-rare MCP → wrap it
in a Skill Claude reads on demand instead of loading always.
- **Completion criterion:** enabled tool count < 50, or the over-budget servers named for disconnect.

## Step 3 — Clear vs compact
- **`/clear`** — full reset. Between UNRELATED tasks (new feature/bug/project). One task = one chat.
- **`/compact`** — squeeze, keep the thread. Mid-task when the SAME job's chat gets long.
- Rule: new task → `/clear`; long task still going → `/compact` at ~60% (early enough to
  compress cleanly; past 85% there's nothing healthy left). Never grind a 90%-full window.
- Goal-scoped compact: "Compact to: working code · 3 decisions that mattered · 1 gotcha ·
  next 2 steps. Drop false starts and pasted files."
- **Completion criterion:** the exact `/clear` or `/compact` to run is chosen.

## Step 4 — CLI over MCP
A CLI loads NOTHING up front — Claude runs it on demand and only the result returns. "Anytime
you can move from an MCP to a CLI, do it." Before adding an MCP, ask: is there a CLI? (A
Playwright CLI did an MCP's job for ~90k fewer tokens.) Install the CLI and its matching Skill
together so Claude knows how to drive it.
- **Completion criterion:** each heavy MCP has a CLI-substitution verdict.

## Step 5 — Model ladder
Cheapest capable rung wins. **Haiku** — quick edits, renames, summaries. **Sonnet** — default
workhorse, real building. **Opus** — hard bugs, architecture, deep planning. Rule: start one
rung LOWER than you think; climb only if it stalls. `/model` switches; `/model opus-plan` plans
on Opus then auto-drops to Sonnet for execution (worth it for multi-file refactors, not
one-line fixes). Put `folder · model · context %` in `/statusline` so you can see the rung.
- **Completion criterion:** the session is on the lowest rung that fits the task.

## Red-MCP triage (when a server shows red)
Run `/mcp`, read the error line (right ~80% of the time), then in order, stop when green:
1. **Key** — missing/wrong API key (#1 cause). Re-paste the full value, no stray spaces/quotes.
2. **Installed** — server package absent ("command not found") → install per its docs.
3. **Restart** — config is read at startup; fully quit and reopen Claude Code.
4. **Typo** — one wrong char / missing comma in the config entry breaks it; validate the file.
- **Completion criterion:** the server is green, or the failing check is named for the operator.

## Related
`connector-routing` picks WHICH substrate (MCP / CLI / Composio); this skill triages what a
session already loaded. Model tiers follow the Anthropic-Max ladder.
