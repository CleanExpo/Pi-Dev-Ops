# Orchestration playbook — the method behind each gate

Read this before opening any gate past G1. It carries the appetite classifier, the specialist
routing menu, the research integrity bar, the tier ladder, and the Executive-Read template with
a worked example. The governing rule for everything here: **the baseline you must beat is a bare
Fable-5 answer with the FABLE_PLAYBOOK already in context.** If opening a gate wouldn't change
the answer, don't open it.

## G1 — Appetite classifier
One cheap read, no tools. Score the goal on two axes and route:

| Signal | Small (answer directly) | Broad (open gates) |
|---|---|---|
| Scope | one question, one file, one known pattern | spans domains, systems, or unknowns |
| Reversibility | trivially undoable | hard/expensive to unwind |
| Unknowns | you already hold the facts | turns on an external/unverified fact |
| Consequence | low blast radius | irreversible or high blast radius |

Any-small-on-all-axes → **direct answer**, jump to G7, dispatch nothing. Mixed → open only the
specific gates the broad axes point to (an unknown fact opens G3; cross-domain opens G4; an
irreversible/high-blast-radius call opens G5/G6). Being founder-facing or client-facing does
**not** by itself open any gate — every `/nexus` goal is founder-facing by construction, so
that alone is never the signal; only an unknown fact, cross-domain breadth, or irreversibility
is. The null case is real and common: a well-specified internal task correctly warrants zero
research, zero specialists, zero verification.

## G4 — Specialist routing menu (a menu, never a quota)
Deploy the *fewest* specialists that cover the goal's real breadth. Default fan-out is zero;
default cap is ≤3; escalate past that only when named needs demand it. Each entry earns its slot
against a stated need or it does not run. **Entries within a row are alternatives — pick the one
that matches the specific need, not a bundle to dispatch together** (e.g. a go-no-go decision
takes `ceo-board` *or* `boardroom`, not both — they are overlapping deliberation mechanisms).
For a research-shaped goal, G3's own per-perspective fan-out IS the research mechanism; only add
`source-ingest`/`storm` here if the goal needs credibility-tiering or perspective breadth beyond
what G3 already ran.

| Task shape | Candidate specialists (pick only what the need demands) |
|---|---|
| Code / refactor / architecture | `Explore` (recon), `design-pressure-test` (pre-build), `opus-adversary` (post-draft), `judge` (gate) |
| New domain vocabulary / entities | `grill-with-docs` (establish ubiquitous language + ADRs) |
| Outward-facing / market / competitor | `source-ingest` (credible data), `storm` (multi-perspective), `eeat` (trust signals) |
| Content / SEO / GEO | `seo`, `geo-optimization`, `eeat`, `marketing-orchestrator` |
| Ship / go-live readiness | `readiness-architect`, `qa-lead`, `readiness` gates |
| Strategic / go-no-go decision | `ceo-board` (deliberation), `boardroom` (multi-model triangulation), `judge` |
| Cross-domain (≥3 of the above) | `specialist-council` — one call returns `{verdict, must_fix, suggestions}` |
| Finance / growth / infra / support metrics | senior agents CFO / CMO / CTO / CS (Pi-Dev-Ops swarm) |

Dispatch mechanics: fan out as parallel `Agent` calls in one message (or a `Workflow` for a
pipeline). Wrap each subagent prompt in the Nexus Prompt (`references/NEXUS_PROMPT.md`) at its
calibrated tier. Reconcile their condensed returns — do not paste raw subagent output into the
answer.

### Tier ladder for dispatched seats (nexus calibration)
- **Fable 5** — final cross-seat synthesis / the judgment call itself. Not routine dispatch.
- **Opus 4.8** — security, architecture, adversarial/verification seats; ambiguity that is
  costly to get wrong.
- **Sonnet 5** — default execution: recon, drafting, known-pattern work.
- **Haiku 4.5** — mechanical, single-increment sub-tasks; escalate after 2 failed verify cycles.

### Recursion + cost guard (mandatory when G4 opens)
A dispatched specialist must never re-enter this orchestrator (no nexus-inside-nexus). Dispatch
depth is capped at 1 level. Bind the whole gate to the estate kill-switches: honour
`TAO_HARD_STOP` (the `~/.claude/HARD_STOP` file) and `TAO_MAX_COST_USD`; if a fan-out would
exceed the cost ceiling, narrow the bench first.

## G3 — Deep-research integrity bar
The failure mode is confident consensus-mush wearing a bibliography. Guard it:

1. **Credibility ladder (tier is assigned by the ladder, never self-declared).**
   - Tier 1: primary — the actual code/logs/schema, official vendor docs, first-party data,
     regulatory/standards text, named-author expert work.
   - Tier 2: reputable secondary — established outlets, peer-reviewed summaries, maintained docs.
   - Tier 3: discovery leads only — blogs, forums, SEO listicles, social. Never load-bearing.
   Reuse `source-ingest`'s whitelist; pass a WebSearch `allowed_domains` list where possible.
2. **Corroboration bar.** Every load-bearing claim needs ≥1 Tier-1 source OR ≥2 *independent*
   Tier-2 sources. A single source of any tier ships tagged `unverified`. (LLM citation
   hallucination runs 14-95% — a URL is a lead, not proof, until fetched and checked.)
3. **Gap-mining (its own step).** Name the claim the top results all repeat. Task a subagent to
   find *credible sources that contradict it*. Report ≥1 defended divergence from the consensus,
   or state plainly "no non-consensus insight found" — never manufacture one (that is the
   volume-scaling / fabrication anti-pattern).
4. **Honest degradation.** If margot deep_research is unreachable or off-limits, say "deep tier
   did not run — WebSearch-only" rather than silently degrading while asserting depth.

Deliverable name is honest: "credibility-weighted, corroborated, divergence-surfaced research",
not "the 1% insight". The insight, if it exists, is the defended divergence — earned, not claimed.

## G7 — Executive Read (the enforceable template)
Every `/nexus` answer opens with this block, in plain language, decision-first. Everything
technical goes *below the fold* under a `--- detail ---` line.

```
DECISION — <the call, one sentence, no hedge>
WHY IT MATTERS — <what this changes for the business, 1-2 sentences>
RISK — <the single most dangerous thing that could still go wrong>
WHAT I'D DO NEXT — <the concrete next action, owner if relevant>
[when G3/G6 ran] CONSENSUS vs US — <what everyone assumes> / <our defended divergence, and what would change it>
```

**Register ban-list (never above the fold):** consequence-tree, flip-rate, tier, contract,
must_fix, subagent, fan-out, corroboration bar, Jaccard, token. Say the plain-language thing
instead ("we checked it against a second, independent reviewer" not "flip-rate via opus-adversary").
**Length cap:** the Executive Read is ≤120 words. If the decision needs more, the surplus is
detail and goes below the fold.

### Worked example (founder-legible)
Goal typed: `/nexus should we move RestoreAssist's judge lane to Fable 5?`

```
DECISION — Not yet. Keep RestoreAssist's review lane on the current model for now.
WHY IT MATTERS — That lane reads customers' insurance-claim data, and the newer model
must keep a 30-day copy of everything it sees — a compliance risk on client files we
shouldn't take without a data check first.
RISK — If we're wrong about which parts of the lane touch client data, we either block a
cheap upgrade for no reason, or expose claim data. A one-page data map settles it.
WHAT I'D DO NEXT — I'll draft that data map (which review steps see claim files) and bring
it back; if it comes back clean, the upgrade is a one-line switch.
CONSENSUS vs US — The obvious read is "the new model is cheaper per answer, so switch."
Our divergence: cheaper-per-answer is true for internal reviews but the retention rule flips
the maths on client data. What would change it: a data map showing the lane never sees
client files.
--- detail ---
Covered-Model 30-day retention (no ZDR); RA dispatch fanOut/judge tiers in lib/agents/routing/
types.ts:38; Board directive 2026-07-05 (RestoreAssist deferred pending client-data
classification); verified via opus-adversary flip-test of the retention claim.
```

That is the shape: a marketing/design founder can act on the top five lines; the engineer-register
evidence is intact but below the fold.
