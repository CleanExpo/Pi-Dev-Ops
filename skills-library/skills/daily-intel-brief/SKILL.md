---
name: daily-intel-brief
description: Morning intelligence sweep — type /daily-intel-brief [topics] to pull GitHub trending, X headlines, YouTube momentum (views-vs-subs signal), and web news for the estate's domains into one dated vault brief. Raw signal over analysis.
argument-hint: "[topic override — default: AI/agents, restoration industry, SEO/GEO]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write, Agent, WebSearch, WebFetch, ToolSearch
---

# daily-intel-brief — know what moved overnight

One dated brief answering "what changed in my domains since yesterday" — GitHub, X, YouTube,
and web headlines in a single glance. The deliverable is curated RAW SIGNAL with links;
trend-analysis prose is explicitly second-class (source's own verdict: hit-or-miss).

## When to invoke

- Morning, alongside `/inbox-triage` (they are the two halves of the morning routine).
- Before content planning, a Board session, or a competitive decision that needs "current
  as of today" grounding.
- You are about to claim "X is the latest" from model memory — stop, run this instead.

## Core procedure

1. **Set topics.** Default: AI/agents + Claude ecosystem, restoration industry (RA/DR/NRPG),
  SEO/GEO. Argument overrides.
   - Done when: 2-4 named topic lanes.
2. **GitHub lane** (`gh api` — no auth gaps, run first):
   `gh api "search/repositories?q=<topic>+created:>{7d ago}&sort=stars"` for the week's new
   repos, same query with `created:>{30d ago}` for the month, plus star-velocity standouts.
   Emit top 5 per window: name, stars, one-line what-it-is, link.
   - Done when: three windows populated with real API results.
3. **X + web lane.** Exa-first with one live availability check, falling back
   WebSearch → WebFetch per the estate's Exa-flaps ladder — never silently skip a lane.
   Pull the day's headlines + notable posts from key accounts (Anthropic/Claude team,
   competitor launches, industry regulators).
   - Done when: each topic lane has ≥3 dated, linked items or an explicit "quiet day" line.
4. **YouTube lane.** Search each topic for uploads <7d old. The signal is views
   DISPROPORTIONATE to subscriber count (10k views on a 2k-sub channel outranks 10k views
   on a 1M-sub channel). List title, channel, views/subs, link. Deep synthesis of any video
   is a handoff to `nlm-skill`, not done here.
   - Done when: ≥3 momentum candidates or explicit "none".
5. **Brief.** Write the report (format below). End with ≤3 "worth a deeper look" pointers,
   each naming the follow-up skill (`deep-loop`, `nlm-skill`, `source-ingest`).
   - Done when: file exists; every item carries a link and a date.

## Output format

`~/2nd Brain/2nd Brain/Briefs/YYYY-MM-DD-intel.md` — frontmatter `type: brief`,
`created: YYYY-MM-DD`; sections: GitHub (3 windows) / X + Web per lane / YouTube momentum /
Worth-a-deeper-look. Every item: one line + link + date. (`Briefs/` is the vault's dated
agent-briefs folder — shared with `inbox-triage`; create it on first run.)

## Calibration

- Full run ≤ 8 minutes, ≤ 12 external queries. Depth belongs to `deep-loop`.
- Brief ≤ 120 lines. Longer means analysis crept in — cut prose, keep signal.
- To schedule it, wire through `curator-scheduled-tasks`; any alerting layered on top fires
  edge-triggered only (state CHANGE, never per-run).

## What this skill is NOT

- Not `deep-loop` — that is one-topic research DEPTH; this is fixed-lane daily BREADTH.
- Not `source-ingest` — nothing here enters the citable source library; promote items there
  when they deserve citation.
- Not `empire-status` — that reads internal systems; this reads the outside world.
- Not a trend-analyst: recommendations are limited to the ≤3 deeper-look pointers.

## Hard rules

1. Every item carries a link and a date — an unlinked claim is model memory, not intel.
   (No-false-recordings directive 2026-07-15.)
2. A lane that fails (API down, auth gap) is reported as failed — never padded from memory.
3. Views-vs-subs beats raw views for YouTube ranking; raw-view ranking regresses to
   celebrity channels and misses the actual signal.

## Provenance

- Source: Chase AI personal-assistant system — https://www.youtube.com/watch?v=gUv7VqcRzok
- Vault: `Wiki/claude-personal-assistant-system-2026-07-15-ingest.md` (brief design,
  views-vs-subs signal, raw-data-over-analysis verdict).
