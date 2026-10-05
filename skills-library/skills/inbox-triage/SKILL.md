---
name: inbox-triage
description: Morning email triage — type /inbox-triage to classify the last 24h of Gmail into leads / urgent / warm / partners / meetings / noise, research real leads, draft (never send) replies, and drop a one-glance brief into the vault.
argument-hint: "[hours to look back, default 24]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write, Agent, WebSearch, WebFetch, ToolSearch
---

# inbox-triage — bucket, research, draft, brief

Turns the morning inbox read into a five-minute glance: every message bucketed, real leads
pre-researched with a go/no-go recommendation, replies drafted for approval, one report in
the vault. Phill stays the arbiter on every send.

## When to invoke

- Start of the working day, or after any >24h away from the inbox.
- Before a discovery call, to pull the sender's thread history and background in one pass.
- You are about to hand Phill a raw inbox summary with no recommendations — stop, run this.

## Core procedure

1. **Fetch.** Read the lookback window (default 24h) from Gmail. Route: check
   `library/connections.md` for the live Gmail plane (claude.ai connector vs Composio
   substrate — prefer Composio when both are up, per estate memory). If neither
   authenticates, STOP and report the auth gap — never fabricate inbox state.
   - Done when: message list with sender/subject/body-preview is in hand.
2. **Bucket.** Classify each message: **leads** (new business for RA / CARSI / CCW / Unite /
   Synthex), **urgent** (deadline, outage, founder-named), **warm** (ongoing client/partner
   threads), **partners** (sponsorship/collab/vendor offers), **meetings** (invites,
   reschedules), **noise** (newsletters, notifications, cold spam).
   - Done when: every message has exactly one bucket.
3. **Act per bucket.**
   - **leads** → validate coherence (budget, timeline, real intent vs form spam); for real
     ones run a background WebSearch on the company; output go/no-go + one-line why + a
     drafted reply with the booking link.
   - **urgent** → drafted reply each.
   - **partners** → drafted boilerplate response pointing at the relevant rate/media info.
   - **warm / meetings** → one-line status each; flag anything stale per the
     stale-action-items rule (verify current thread state before drafting).
   - **noise** → count only, listed at the report tail.
   - Done when: every non-noise message has an action artifact or a one-liner.
4. **Report.** Write the brief (format below) to the vault and surface drafts for approval.
   - Done when: report file exists and the reply names where every draft lives.

## Output format

`~/2nd Brain/2nd Brain/Briefs/YYYY-MM-DD-inbox.md` — frontmatter `type: brief`,
`created: YYYY-MM-DD`; sections per bucket in the order above; each lead entry:
sender, company, ask, budget signal, research digest (2-3 lines), **GO / NO-GO + why**,
draft location. Drafts are created as Gmail drafts when the connected plane supports it,
otherwise inline in the report under the entry. (`Briefs/` is the vault's dated
agent-briefs folder — shared with `daily-intel-brief`; create it on first run.)

## Calibration

- Full run ≤ 10 minutes, ≤ 3 web searches per lead. A lead needing more research than that
  is a discovery-call question, not a triage question.
- >5 "urgent" items usually means over-triggering — urgent requires a deadline, an outage,
  or the founder named in the ask.

## What this skill is NOT

- Not `email-listener` — that converts inbound mail into Pi-CEO sessions via webhook; this
  is the on-demand/morning human-facing triage pass.
- Not a sender: it never sends anything. Draft + surface for Send is the decision-rights
  boundary.
- Not `sow-draft`/`stripe-milestone-invoice` — a GO lead hands off to those, it doesn't
  absorb them.

## Hard rules

1. NEVER send. Drafts only. (Outbound is founder-gated estate-wide.)
2. Never fabricate inbox state — if the mail plane fails, the report says so and stops.
   (No-false-recordings directive 2026-07-15.)
3. Verify thread state before drafting on warm items — action items observed to go stale.
4. GO/NO-GO always carries the one-line why; a recommendation-free list is a violation.

## Provenance

- Source: Chase AI personal-assistant system — https://www.youtube.com/watch?v=gUv7VqcRzok
- Vault: `Wiki/claude-personal-assistant-system-2026-07-15-ingest.md` (bucket design,
  per-bucket actions, human-arbiter rule).
