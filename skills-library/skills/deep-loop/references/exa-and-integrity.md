# Exa freshness lane + the research-integrity bar

Read when a proposer runs the freshness lane (D4). Exa is the PRIMARY lane because deep-loop's
whole value is CURRENT data. It went down for 3 days in July 2026 (HTTP 402 x402 paywall — memory
`reference_exa_down_x402`; recovered 2026-07-11), so the ladder is mandatory and degradation is
NEVER silent.

## Load the Exa tools first (this environment)

Exa tools are DEFERRED here — their schemas are not loaded until requested. Before the first
call, run: `ToolSearch "select:mcp__claude_ai_Exa__web_search_exa,mcp__claude_ai_Exa__web_fetch_exa"`.
They are STABLE-named claude.ai connector tools (connections.md), not hashed UUIDs — do not
try to re-resolve their names at runtime.

## The ladder — try IN ORDER, record which lane actually ran (never a race, never silent)

0. **Absent check** — if ToolSearch returns no Exa match (connector absent — the normal
   headless/cron/watch case, since claude.ai connectors need interactive auth), skip straight to
   WebSearch and stamp the lane `Exa-absent`. Watch/headless runs are WebSearch-tier by default.
1. **Exa** — `web_search_exa` (neural discovery, date-filtered by `fresh-since`) + `web_fetch_exa`
   to read. For anything load-bearing, FETCH the top Tier-1/2 URLs — a snippet is a lead, full
   text is evidence (a URL is not proof until fetched and checked; LLM citation hallucination 14–95%).
2. **WebSearch** — on Exa 402/x402 / 5xx / timeout / empty. Seed `allowed_domains` from the
   source-ingest credibility whitelist (who.int, nih.gov, abs.gov.au, nature.com, oecd.org,
   doi.org, .gov, .edu, IICRC/ISO, vendor docs) so the fallback still yields Tier 1–2, not SEO chum.
3. **WebFetch** — read a specific known URL (gap-round contradiction/primary fetches). Fails on
   auth/JS walls — say so.

The FIRST lane that returns usable results serves the seat. Each claim STAMPS `lane`. The report
states ONCE, honestly, which lane(s) served the round: 'Freshness lane: Exa (12 fetched)' or
'Freshness lane: Exa DOWN (x402) → WebSearch fallback'. Never assert Exa freshness you did not get.

## Query shaping + freshness

- Shape the query to the seat's perspective/gap, not the bare topic (skeptic → 'criticism/
  limitations of X 2026'; economics → pricing/filing/market-share terms).
- Round-N proposers query the SPECIFIC gap/contradiction (skip discovery — fetch it directly).
- `fresh-since` default = 12 months; flag overrides 30d / 6mo / ISO date; watch-mode sets it to
  the last-run timestamp so each re-run reads only genuinely new material.

## Research-integrity bar — INHERITED, not re-encoded

Deep-loop uses the nexus **G3** bar verbatim. Read the SSOT:
`~/.claude/skills/nexus/references/orchestration-playbook.md` §'G3 — Deep-research integrity bar'.
It owns the credibility ladder, the corroboration bar, gap-mining, and honest degradation — the
tier definitions and thresholds live THERE, only there. **Deep-loop deltas only:** tier is assigned by
the ladder, never by Exa's ranking (a fresh Exa URL is still Tier 3 until the ladder says
otherwise); the corroboration bar runs at Aggregator-A1 each round and again at the D6 judge;
gap-mining is not a one-off step — it is the swarm's round-to-round engine (D3).

## Where margot + source-ingest fit

`margot deep_research` is a SEPARATE optional proposer modality (Tier-1 corpus-anchored synthesis),
not a rung of this ladder and not a substitute for Exa on current-data topics — honest degradation
('deep tier did not run — Exa/WebSearch only') if unreachable. The `source-ingest` whitelist is a
SHARED ASSET (allowed_domains + domain→tier); its margot-first PIPELINE is deliberately EXCLUDED —
the proposer swarm is the research engine. Optional Sources/ write-back reuses its corpus
(reuse-before-rescrape).
