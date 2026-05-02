---
name: daily-6-pager
description: Stripe-style daily executive brief assembled from CFO + CMO + CTO + CS snippets, the latest Margot deep-async insight, and RA-1842 (iOS release) status. Cron-fired at user-local 06:00. Routes through pii-redactor + draft_review HITL gate. Closes Wave 4 A5 of the senior-agent slate (RA-1863).
owner_role: CoS
status: wave-4
---

# daily-6-pager

The morning Pi-CEO 6-pager — every senior agent's prior-cycle output composed into one page the founder can read in 10 minutes.

## Why this exists

Sahil Lavingia (Gumroad) and the Collisons (Stripe) both built their solo-CEO leverage around the daily 6-pager. The founder reads, comments, doesn't synchronously discuss. Pi-CEO automates the production of that artefact.

Each senior agent (CFO / CMO / CTO / CS) writes its own snapshot to a per-bot jsonl ledger every cycle. The 6-pager assembler reads the **last per-business row** from each ledger, runs the same `detect_breaches` + `assemble_daily_brief` functions the senior bots use internally, and stitches the output into a 6-page composition.

## Page structure

```
📋 Pi-CEO daily 6-pager — {date}

1. 💰 CFO daily — burn / runway / NRR / GM / spend gate queue
2. 📈 CMO daily — LTV:CAC / CPA / channel mix / ad-spend gate queue
3. ⚙️ CTO daily — DORA quartet / p99 / uptime / production PR queue
4. 💬 CS daily — NPS / FCR / GRR / first-response / refund queue
5. 🧠 Margot insight of the day — latest deep-async / topic / ts
6. 📱 RA-1842 (iOS release) — state / last update / note

—
React 👍 to ack · ❌ to flag · ⏳ to defer per section.
```

## Trigger

| When | What |
|---|---|
| Cron 06:00 UTC (configurable per-business via `TAO_SIX_PAGER_HOUR_UTC`) | `assemble_six_pager()` → `pii_redactor.redact()` → `draft_review.post_draft()` to `REVIEW_CHAT_ID` |
| Founder Telegram intent `"6-pager"` / `"brief me"` / `"daily picture"` | CoS bot routes to `assemble_six_pager()` and replies with the result |
| B3 Voice Mode (RA-1866) | After assembly, optionally produce a voice variant and send via `telegram-bot/voice_handler.py` |

## Implementation

```
swarm/six_pager.py:assemble_six_pager(repo_root=None, date_str=None) -> str
  ├── _cfo_section  — reads .harness/swarm/cfo_state.jsonl
  ├── _cmo_section  — reads .harness/swarm/cmo_state.jsonl
  ├── _cto_section  — reads .harness/swarm/cto_state.jsonl
  ├── _cs_section   — reads .harness/swarm/cs_state.jsonl
  ├── _margot_section — reads .harness/margot/insights.jsonl
  └── _ra_1842_section — reads .harness/ra-1842-status.json
```

Each section degrades gracefully when its upstream ledger is missing (returns a one-line "no recent snapshots" placeholder rather than failing the whole brief).

## Safety bindings

- **pii_redactor in front of every send.** Names, emails, vendor strings flow through redaction.
- **draft_review HITL gate** — never auto-sent.
- **Kill-switch aware** — daily fire is queued (not sent) on `TAO_SWARM_ENABLED=0`.
- **Read-only.** No SDK calls, no external API calls. Pure file-read composition.

## When NOT to use

- Real-time triage — that's CoS bot via `intent_router.py`
- Per-bot deep-dive — open the relevant senior-agent's own jsonl ledger directly
- Marketing artefact production (campaign copy, landing pages) — `marketing-orchestrator` family
- Code generation / PR creation — `pipeline.py` + `tier-orchestrator`

## Verification (Wave 4 A5)

1. With all four senior-agent ledgers populated, brief assembles in <2s
2. Missing CFO ledger → `_cfo_section` emits placeholder, brief still renders
3. Missing Margot insight → section emits placeholder, brief still renders
4. Missing RA-1842 status → section emits placeholder, brief still renders
5. Page is composable into a Telegram message (≤4096 chars) — caller may need to chunk; assembler does not enforce length

## References

- Blueprint: `/Users/phill-mac/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md` §"Solo-CEO leverage patterns" (the 6-pager paradigm)
- Parent ticket: <issue id="RA-1863">RA-1863</issue> (epic <issue id="RA-1858">RA-1858</issue>)
- Composes: `swarm/cfo.py` · `swarm/cmo.py` · `swarm/cto.py` · `swarm/cs.py`
- HITL gate substrate: `swarm/draft_review.py`
- Voice variant (Wave 4 B3): <issue id="RA-1866">RA-1866</issue>
