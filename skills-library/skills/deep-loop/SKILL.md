---
name: deep-loop
description: Operator command to drill ONE topic to primary sources with current data — iterative multi-agent research that deepens each round until the topic saturates, delivered as a founder-legible decision over a fully cited report; watch mode re-runs on an interval and pings only on material change.
argument-hint: "<topic> [depth: quick|standard|deep] [rounds: N] [fresh-since: 30d|6mo|DATE] [watch: 6h|daily|weekly] [perspectives: \"a, b, c\"] [saturation-k: N] [save: vault|here|off] [budget: $N]"
disable-model-invocation: true
# the two Exa names are the documented stable-name exception to the no-hardcode-mcp rule (claude.ai connector, see references/exa-and-integrity.md)
allowed-tools: Read, Grep, Glob, Bash, Agent, Task, Workflow, WebSearch, WebFetch, Skill, ToolSearch, mcp__claude_ai_Exa__web_search_exa, mcp__claude_ai_Exa__web_fetch_exa, mcp__margot__deep_research
---

# deep-loop — the one-topic research-depth engine

> **INVOCATION — read this first.** `disable-model-invocation: true` means calling this skill
> through the `Skill` tool **errors by design** (it stops the sub-agent fleet auto-firing an
> expensive swarm). When the operator types `/deep-loop <topic>`, **Read this file and run the
> gates below inline** — never `Skill(deep-loop)`. Mirrors `/nexus`.

## What this is / is not

The estate's **single-topic depth engine**: Exa-first freshness + honest Mixture-of-Agents
(arXiv 2406.04692) + a swarm loop that re-targets each round at the previous round's open gaps.
It **inherits nexus G1/G3/G6/G7 by pointer** to
`~/.claude/skills/nexus/references/orchestration-playbook.md` — zero duplication — and is itself
the depth engine `/nexus` may dispatch at its G3/G4. It is NOT a quick lookup (D0 downshifts
those), NOT `storm`'s neutral long-form article (route out, don't nest), NOT the built-in `/loop`
interval runner (watch-mode composes with it), and NOT the lighter built-in `deep-research`
single-pass harness — use deep-loop when the topic needs iterative deepening and current data.

## Invocation and flags (English flags, smart defaults)

| Flag | Values | Default |
|---|---|---|
| `depth:` | quick (3 proposers) / standard (4) / deep (6, K=2, 5 rounds; Opus aggregators only with `budget:`) | standard |
| `rounds:` | N (hard cap) | 3 (deep: 5) |
| `fresh-since:` | 30d / 6mo / ISO date | 12 months |
| `watch:` | 6h / daily / weekly — recurring re-run via built-in /loop | off |
| `perspectives:` | "a, b, c" — overrides auto-discovery | auto (3–6) |
| `saturation-k:` | consecutive dry rounds before stop | 1 (deep: 2) |
| `save:` | vault / here / off | vault |
| `budget:` | $N — raises TAO_MAX_COST_USD for this run only | ceiling as set |

An underspecified topic gets 2–3 tight clarifying questions before anything fires.

## Live progress contract

One glanceable line per event, so the operator can act on the log alone:
`R{n}.L{layer} {role}×{count} [{lane}] … {new}/{total} claims verified · ${spend}`
Plus one line per stop-condition trigger naming the guard that fired.

## The gates

**D0 — Appetite (always).** Classify with the nexus **G1** classifier (by pointer). A
small/well-specified question → answer directly or run a single Exa pass and STOP — the
apparatus must not fire for a narrow ask.
- Completion: appetite named; the null case honoured.

**D1 — Frame & mine (always).** Ground in the vault before reaching outward:
`node "$HOME/2nd Brain/2nd Brain/_system/brain.js" find "<topic>"` (nexus-recall; self-heal the
index on a miss). Restate the topic as an outcome. Discover 3–6 research perspectives from the
menu in [`references/moa-swarm-playbook.md`](references/moa-swarm-playbook.md); the
`perspectives:` flag overrides.
- Completion: perspectives named; prior context mined; recall hit/miss recorded.

**D2 — MoA round.** Each round: **L1 proposers** (Sonnet, one perspective or one gap each, own
retrieval down the Exa ladder) → **L2 aggregators ×2** (each receives ALL proposer outputs:
A1 corroborate/reconcile, A2 divergence/gap-miner; each must emit a delta note) → **L3 synthesist**
(Opus, the only seat that writes claims to the corpus; emits the gap ledger + running Executive
Read + materiality verdict). Full layer spec, perspective menu, and gap-ledger schema are in
[`references/moa-swarm-playbook.md`](references/moa-swarm-playbook.md); read it before opening D2.
- Completion: ≥1 round ran; every load-bearing claim tiered + corroborated or tagged unverified.

**D3 — Swarm loop.** Round 1 is breadth (perspectives). Round N (≥2) is depth: rank the previous
round's gap ledger by load-bearing-ness and seed a FRESH proposer swarm one-per-gap (floor 2);
the corpus carries forward read-only. Gaps are the literal task list of the next round — depth
compounds, breadth is never re-run. An empty ledger stops the loop.
- Completion: each round after the first traces to named gaps.

**D4 — Exa lane + integrity.** Exa is the primary freshness lane behind a mandatory, never-silent
ladder: **Exa → WebSearch (whitelist-seeded) → WebFetch** — per
[`references/exa-and-integrity.md`](references/exa-and-integrity.md) (includes the ToolSearch
preload step for the deferred Exa tools). The research-integrity bar is nexus **G3** verbatim,
by pointer: credibility ladder, corroboration bar, gap-mining, honest degradation.
- Completion: no naked single-source load-bearing claim; the lane that actually ran is reported.

**D5 — Stop conditions.** Five guards — HARD_STOP, TAO_MAX_COST_USD (pre-round projection),
round cap, per-round agent caps, saturation (K consecutive dry rounds; dual-condition test +
cheap pre-filter) — specified in
[`references/moa-swarm-playbook.md`](references/moa-swarm-playbook.md). Caps always beat
saturation. Partials persist to disk after every round.
- Completion: the stop reason is recorded in the report footer.

**D6 — Adversarial verify.** Route the final corpus through `opus-adversary` (nexus **G6**, by
pointer): flip-test each load-bearing claim; a claim that flips is downgraded to
"assumption (unverified)" before it can reach the Executive Read.
- Completion: load-bearing claims survived an independent adversary, or were downgraded.

**D7 — Deliver.** Open with the nexus **G7** Executive Read (by pointer — ≤120 words, plain
language, register ban-list). Below `--- detail ---`: the cited report with `{source URL, tier}`
per claim, the unverified list, the defended divergence (or "none found"), the REMAINING gap
ledger, and the method footer (rounds, stop reason, active lane per round, spend). `save:vault`
writes the sanctioned Outcomes note (`~/2nd Brain/2nd Brain/Outcomes/YYYY-MM-DD-<slug>.md`) +
OKF regen via the generator; `watch:` routes 6h→built-in `/loop`, daily/weekly→`schedule`, with
edge-triggered pings. Details in
[`references/output-and-watch.md`](references/output-and-watch.md).
- Completion: decision-first top; cited detail below; partials labelled at the top.

## Guards (mandatory whenever D2 opens)

HARD_STOP, cost projection, round/agent caps, structural recursion depth-1, and the model
ladder are specified ONCE in [`references/moa-swarm-playbook.md`](references/moa-swarm-playbook.md)
§Guards — the ORCHESTRATOR checks them between rounds. Degradation is stated, never silent.

## Mechanism

The orchestrator owns the swarm loop, guards, and per-round persistence; each MoA round executes
as ONE **Workflow** call (or batched parallel `Agent` calls where Workflow is unavailable). The
canonical orchestrator loop + round script live in
[`references/workflow-script.md`](references/workflow-script.md) — never inline them here.
