# Canonical mechanism — orchestrator-gated rounds

**Division of labour (this is the guard fix — do not regress it):** Workflow scripts have NO
filesystem access, so HARD_STOP / cost checks / partial persistence CANNOT live inside a
workflow. The **orchestrator** (the session running this skill, which has Bash/Read/Write) owns
the swarm loop: between rounds it checks `~/.claude/HARD_STOP`, projects the next round's cost
against `TAO_MAX_COST_USD` (narrow the bench or stop — never overshoot), and Writes the running
synthesis + Executive Read to disk (partial-on-interrupt). Each **MoA round** then executes as
ONE Workflow call (below) — or, where the Workflow tool is unavailable, as batched parallel
`Agent` calls: all L1 proposers in ONE message, then both L2 aggregators in one message, then L3.
Dispatch leaf seats WITHOUT orchestration tools (e.g. `Explore`-type agents, which lack the
Agent tool) so sub-swarms are impossible by construction; the LEAF prompt is belt-and-braces.

## Orchestrator loop (inline pseudocode — the session runs this, not a script)

```
stop = null; ran = 0; ledger = null; out = null
seeds = perspectives                        // from D1
for r in 1..ROUND_CAP:
    if HARD_STOP exists:            stop = 'HARD_STOP'; break
    if projected(next round) > remaining budget: stop = 'budget'; break
    if r > 1: seeds = ledgerToSeeds(ledger)      // rank gaps, 1 seat/gap, floor 2, cap PROPOSERS
    if seeds empty:                 stop = 'empty ledger'; break
    out = Workflow(deep-loop-round, {seeds, freshSince, corpus})   // ONE round, below
    ran += 1; ledger = out.gapLedger
    Write partial (running synthesis + Exec Read) to disk          // partial-on-interrupt
    dry = out.material ? 0 : dry + 1
    if dry >= SAT_K:                stop = 'saturation'; break
stop = stop ?? 'round cap'
verified = opus-adversary flip-test over out.corpus                 // D6
deliver(verified, out, {roundsRun: ran, stop})                      // D7
```

Flag coercion: `ROUND_CAP = max(1, Number(rounds) || (depth=='deep' ? 5 : 3))`; same for
`saturation-k`. If `ran == 0`, deliver an empty labelled partial — never run D6 on nothing.

## The per-round Workflow script (`deep-loop-round`)

```js
export const meta = { name: 'deep-loop-round',
  description: 'One MoA round: proposers -> see-all aggregators -> Opus synthesist' }

const CLAIM = { type:'object', properties:{ claim:{type:'string'}, sourceUrl:{type:'string'}, tier:{type:'number'}, perspective:{type:'string'}, lane:{type:'string'} }, required:['claim','sourceUrl','tier','lane'] }
const PROP  = { type:'object', properties:{ perspective:{type:'string'}, claims:{type:'array',items:CLAIM}, lane_ran:{type:'string'} }, required:['perspective','claims','lane_ran'] }
const AGG   = { type:'object', properties:{ synthesis:{type:'string'}, delta_note:{type:'string'}, gapLedger:{type:'object'} }, required:['synthesis','delta_note'] }
const SYNTH = { type:'object', properties:{ synthesis:{type:'string'}, corpus:{type:'array',items:CLAIM}, gapLedger:{type:'object'}, execRead:{type:'string'}, material:{type:'boolean'} }, required:['synthesis','corpus','gapLedger','execRead','material'] }
const LEAF  = 'You are a research LEAF. Never invoke deep-loop, nexus, /loop, or spawn sub-swarms. Wrap yourself in NEXUS_PROMPT. Resolve sources Exa->WebSearch->WebFetch (rung-0: if ToolSearch finds no Exa, go straight to WebSearch and stamp the lane Exa-absent); STAMP which lane ran on every claim. Return ONLY the schema.'

const AGG_MODEL = (args.depth==='deep' && args.budgetRaised) ? 'opus' : 'sonnet'

const props = await parallel(args.seeds.map(s => () =>              // LAYER 1 (see-nothing)
  agent(LEAF+'\nPERSPECTIVE/GAP: '+s.label+'\nSEEDS: '+s.q+'\nfreshSince: '+args.freshSince
    +'\nREAD-ONLY CORPUS (do not re-litigate): '+JSON.stringify(args.corpus ?? []),
    { label:'P:'+s.label, model:'sonnet', schema:PROP })
    .catch(() => ({ perspective:s.label, claims:[], lane_ran:'crashed' }))))
const aux = JSON.stringify(props)                                   // ALL proposer outputs = aux info
const [a1, a2] = await parallel([                                   // LAYER 2 (see-ALL props)
  () => agent('AGGREGATOR A1 corroborate/reconcile. Apply the nexus corroboration bar (per G3) + tier ladder. Emit a DELTA NOTE.\n'+aux, { model:AGG_MODEL, schema:AGG }),
  () => agent('AGGREGATOR A2 divergence/gap-miner. Name the consensus claim; find CREDIBLE contradictions; defended divergence or "none found"; emit the gap ledger. Emit a DELTA NOTE.\n'+aux, { model:AGG_MODEL, schema:AGG }),
])
return await agent('FINAL SYNTHESIST. Merge into the cumulative corpus, emit gapLedger + running execRead, set material=true only if this round added verified load-bearing claims or changed the gap set.\nProps:'+aux+'\nA1:'+JSON.stringify(a1)+'\nA2:'+JSON.stringify(a2)+'\nPRIOR CORPUS:'+JSON.stringify(args.corpus ?? []),
  { model:'opus', schema:SYNTH })                                   // LAYER 3
```

Pass `{seeds, freshSince, corpus, depth, budgetRaised}` via the Workflow `args` input. The
orchestrator (not the script) applies the dry-round cheap pre-filter — 0 new URLs AND 0 new
claims → dry without an extra judge call. Long-running/recurring mode is NOT built here — it
composes with the built-in /loop or the `schedule` surface (see `output-and-watch.md`).
