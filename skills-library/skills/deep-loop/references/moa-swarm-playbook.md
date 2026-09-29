# MoA + swarm — the method behind D2/D3

Read before opening D2. Carries the layer spec, perspective menu, round/saturation mechanics,
the gap-ledger schema, and the guards. Governing rule: this is HONEST Mixture-of-Agents
(arXiv 2406.04692, ICLR 2025) — **every aggregator receives ALL previous-layer outputs as
auxiliary context**, not a merge over a fan-out. The research-integrity bar (credibility ladder,
corroboration bar, gap-mining, honest degradation) and the Executive Read are INHERITED from
`~/.claude/skills/nexus/references/orchestration-playbook.md` (G3 + G7) — do NOT restate them here.

## Perspective menu (D1 — discover 3–6, pick what the topic earns; `perspectives:` overrides)

Diversity is ENGINEERED per-seat, never left to emerge. Menu (storm-derived):
regulatory/standards · competitor/market/commercial · technical-internals/how-it-works ·
end-user/affected/adoption · economics/cost/incentives · skeptic/failure-mode/contrarian ·
history/origins/trajectory. Each seat gets a distinct system frame + distinct seed queries +
a distinct primary-lane bias (primary seat → site:.gov/.edu/official; economics → pricing/filings).

## Layer spec (per round, run via the Workflow tool)

| Layer | Seats | Model | Receives | Emits |
|---|---|---|---|---|
| L1 Proposers | quick=3 / standard=4 / deep=6 (cap 6, floor 2 on gap rounds) | Sonnet 5 | one perspective (r1) OR one ranked gap (rN) + read-only corpus | `[{claim,sourceUrl,tier,perspective,lane}]` |
| L2 Aggregators | 2 fixed | Sonnet 5 (Opus only at depth:deep WITH budget:$N raised) | ALL L1 proposer outputs (full array) | improved synthesis + delta note (+ gap ledger from A2) |
| L3 Synthesist | 1 | Opus 4.8 | both aggregators + delta notes + proposer pool | round synthesis, merged corpus, gap ledger, running Exec Read, materiality verdict |
| Judge (post-loop) | 1, once | Opus 4.8 | final corpus | opus-adversary flip-test; flips → 'assumption (unverified)' |

Orchestrator (depth-0, Opus) sits above rounds: it routes, applies stops, never researches.

### L1 proposers
Each does its OWN retrieval down the Exa→WebSearch→WebFetch ladder (`exa-and-integrity.md`).
Every load-bearing claim fetched-and-checked; tier assigned by the ladder, never self-declared.
One seat MAY be the optional margot `deep_research` corpus modality when reachable (honest
degradation if not). `margot`/`source-ingest` are proposer MODALITIES (extra seats), never stages.

### L2 aggregators (see-all; distinct mandates so the layer is additive)
- **A1 corroborate/reconcile** — dedup/cluster; apply the nexus corroboration bar (per G3, the
  SSOT — thresholds live there); tag survivors vs `unverified`; assign tiers; note coverage holes.
- **A2 divergence/gap-miner (FIRST-CLASS stance)** — name the claim every proposer repeats;
  actively search for CREDIBLE contradicting sources; emit a defended divergence or 'none found';
  produce the gap ledger. Never manufacture a divergence.
- **Anti-rubber-stamp:** each aggregator MUST emit a **delta note** ('what I changed from the
  proposers and why'). No delta note ⇒ it did nothing; re-run it once.

### L3 synthesist (Opus, single) — the only seat that writes claims to the corpus.

## Gap-ledger schema (the swarm driver)

```
{ open_unknowns: ["..."],
  contradictions: [{ claimA, claimB, sources:[url] }],
  thin_claims:    [{ claim, sourceUrl, tier }],   // single-source / unverified
  missing_tier1:  ["claim needing a primary source"] }
```

Round N proposers are seeded ONE-PER-GAP, ranked by load-bearing-ness (floor 2, cap = depth count).
The ledger shrinks as gaps resolve; an EMPTY ledger is a stop condition.

## Swarm loop

- **Round 1 (breadth):** proposers seeded from the discovered perspectives.
- **Round N (depth):** orchestrator reads round N-1's ledger, ranks gaps, spawns FRESH proposers
  each targeted at ONE gap (new agents, gap-shaped queries); corpus carries forward read-only.

Gaps are the literal task list of the next round — depth compounds, breadth is never re-run.

## Saturation math (loop-until-dry)

A round is **DRY** when BOTH hold vs the prior round: (1) 0 new verified load-bearing claims AND
(2) the NORMALISED open-gaps signature is unchanged (lowercase gap stems, strip volatile
numbers/dates — same normalisation the watch-mode edge-trigger uses). **Cheap pre-filter:** 0 new
URLs AND 0 new claims → dry WITHOUT spending the Opus judge. Stop after **K consecutive dry
rounds — default K=1** (a dry gap-targeted round means those specific gaps resisted resolution,
not that nobody looked); raise to K=2 for high-stakes via `saturation-k:2` or `depth:deep`.
Saturation is the graceful exit; the caps below ALWAYS win.

## Guards (SSOT — mandatory when D2 opens; the ORCHESTRATOR runs them, between rounds)

Workflow scripts have no filesystem access, so every guard below runs in the orchestrator
session (which has Bash/Read/Write), BEFORE each round is spawned — see `workflow-script.md`.

- Check `~/.claude/HARD_STOP` (TAO_HARD_STOP) before every round → stop, deliver the labelled partial.
- Honour `TAO_MAX_COST_USD`: project the NEXT round's fan-out cost (Opus seats dominate; the
  synthesist's growing corpus is the tail) — if it breaches, don't open the round; narrow the
  bench or deliver the partial. `budget:$N` raises the ceiling for one run only. An un-budgeted
  `depth:deep` run routinely truncating to a partial is intended behaviour, not a failure.
- Round cap default 3 (`rounds:N` / `depth:deep`→5); coerce flags to numbers, floor 1.
  Per-round proposer cap 6, aggregators 2.
- **Recursion depth cap 1 — structural, not just prompted:** dispatch every leaf seat WITHOUT
  orchestration tools (Workflow-subagent seats, or `Explore`-type agents in batched mode — no
  Agent tool ⇒ no sub-swarm; `disable-model-invocation` already hard-blocks deep-loop/nexus
  re-entry via Skill). The LEAF prompt line is belt-and-braces on top.
- Persist the running synthesis + Exec Read to disk after every round (orchestrator Write —
  partial-on-interrupt).

## Model ladder (Fable Free, 2026-07-08)

Orchestrator + final synthesist + judge = **Opus 4.8**. Proposers + aggregators = **Sonnet 5**
(aggregators → Opus only at `depth:deep` with `budget:$N` explicitly raised — the fixed-Opus
tail must never silently blow the daily ceiling). Mechanical single-increment sub-tasks = Haiku 4.5.
**Fable 5 is a per-route carve-out, never the ambient default.** Provider unavailability
(429/5xx) fails over down an ordered chain, never an N× race.
