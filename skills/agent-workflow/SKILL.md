---
name: agent-workflow
description: Use when defining, scoping, promoting, or debugging an agent or ADW — the 5-part agent contract, scoping formula, promotion ladder, and 4-way break diagnostic.
---

# Agent Workflows

## Pre-built ADWs (trigger → deploy)
1. Feature Build: decompose → build → test → review → PR
2. Bug Fix: reproduce → diagnose → fix → verify → commit
3. Chore: apply → lint → test → auto-merge
4. Code Review: read diff → analyze → report
5. Research Spike: research → summarize → recommend

## The 5-part agent contract — name · soul · job · keys · stop
Define every agent as five load-bearing parts in `.claude/agents/<name>.md` (frontmatter
`name` / `description` / `tools:`; body `## SOUL` / `## JOB` / `## KEYS` / `## STOP`). Exactly
five — a sixth ("metrics dashboard", "personality archetype") only dilutes the soul.

1. **Name** — kebab-case handle you'll type 100×. Lowercase, dashes, no cuteness.
2. **Soul** — 4–6 sentences of permanent identity: voice, what it cares about, what it
   refuses to do. Inherited every run — this is what kills generic output. Fix voice by
   editing the SOUL file, never the prompt (prompt fixes evaporate at session close).
3. **Job** — ONE sentence mission with an explicit "do NOT" clause. Won't fit one sentence →
   not scoped, split it. "Sort unread mail into URGENT/RESPOND/FYI/IGNORE, draft 2-line
   replies for URGENT" is a job; "help with my inbox" is a wish.
4. **Keys** — which tools + folders it may touch (set via `tools:`). Tight by default,
   loosened on purpose — fewest tools that do the job, add one back only when needed.
5. **Stop** — how it knows it's done, as something it can literally check ("3 files exist in
   /drafts/[date]/, summary printed"). Vague = wandering; measurable = clean exit.

## Scoping formula — scope · steps · guardrails · report-back
Every brief carries four ingredients: exact scope (which files/folder, nothing wider); steps
in order in plain words; guardrails (explicit "must not"); report-back (what it shows you so
you stay the approver). Test: could you hand the brief to a new assistant and walk away? If
not, it's not scoped yet.

## Promotion ladder — hand-run → /loop → scheduled
An agent earns automation after **5 clean hand-run executions in a row** — not 3, not "it
worked once." Trust is an observation count; runs 1–2 could be luck, by 4–5 you've seen the
weird-data week.
- **L1 hand-run** — you type the command. Every agent starts here.
- **L2 `/loop`** — runs while your session is open, `Esc` reachable. Where most agents live
  for weeks; the test track. (`/loop` auto-expires after 7 days.)
- **L3 scheduled** — runs on the server, laptop closed. Only for proven, boring,
  drafted-output agents. Anything that sends / posts / pays / deletes stays L2 or gets a
  human-approval hook baked in.
- Graduation checklist: confirm 5 logged clean runs · lock SOUL+JOB (unchanged across them) ·
  add a heartbeat log line per run · set a weekly log-review cadence.

## 4-way break diagnostic
"My agent doesn't work" is almost always one of four — and 4 of the 5 are FILE problems, not
prompt problems. Open the `.md` first, the chat second.
1. **Soul drift** ("doesn't sound like me") → SOUL too thin. Rewrite with real voice samples
   + banned words.
2. **Scope creep** ("did too much") → KEYS gave unneeded tools + JOB lacked a "do NOT". Strip
   tools, add the DO-NOT line.
3. **Wandering** ("ran 20 min, produced mush") → no / vague STOP. Add a measurable stop + a
   tool-or-time budget ("if >5 tool calls, pause and ask").
4. **Silent failure** ("said done, nothing there") → a hook blocked it, or wrong path/perms.
   `ls` the real folder yourself; check the hook log + KEYS. Add a self-verify to STOP.
- Bonus — **context bleed** (tone shifts mid-run): the orchestrator forwarded too much
  history; brief subagents with only the input they need.

## Rules
- Keep the roster to 3–5 agents; delete any not run in 30 days.
- Every external action keeps a human approval gate; silence defaults to reject.
- Bottle a wrapper into `.claude/commands/<name>.md` (with `$ARGUMENTS`) only after it runs
  cleanly twice — the slash command is the celebration, not the attempt.
