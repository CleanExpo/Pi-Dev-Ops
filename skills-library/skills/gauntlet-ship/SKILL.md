---
name: gauntlet-ship
description: "The gauntlet for getting a real product to market: grinds a ship backlog to live instead of polishing one surface against a competitor. The bar is a production-observable gate per item, selection is by ship-blocking rank, and the exit is the gate passing in production, observed by an agent that did not build it. Dispatched by gauntlet-loop when the goal is 'ship it' rather than 'beat X'."
---

# Gauntlet Ship

Read `../gauntlet-loop/SKILL.md` first. The loop structure — small pieces, separate builder and
critic, fresh context, binary judgement, no round count — carries over unchanged.

Three things change, and they are the whole skill:

| | gauntlet-loop | gauntlet-ship |
|---|---|---|
| The bar | A named external artifact, judged on taste | A gate a hostile auditor could run against production |
| Selection | The pieces of one surface | Ship-blocking rank across the whole backlog |
| The critic's job | Which is better, ours or theirs | Try to make the gate pass while the defect is still present |

## Why this exists

A gauntlet run on 2026-08-07 ground a pricing page through seven rounds against Stripe's pricing
page. The work was genuinely good — real defects, positive controls, differential gates. It also
ran for a day and a half while row-level security was off on 119 production tables holding `User`,
`Account` and every integration credential, which no piece on the board touched.

The loop was working exactly as designed. It optimised a *surface*, because a surface is what a
named external bar can be pointed at. Nothing in the skill made the most dangerous open item the
next piece, because that item has no competitor to be judged against.

**If the goal is to sell the product, the bar is not a rival's page. It is the thing that must be
true before a customer's data, money or access is on the line.**

## The bar, re-cut for ship work

Same three tests as the parent, different content. A ship bar must be:

- **Binary.** It passes or it fails, and no judge is required. "RLS enabled on every table holding
  customer data, verified by `pg_policy`" works. "Security is solid" does not.
- **Observable in production.** Checkable against the live system, not the repo and not the diff.
  A merged fix is a hypothesis. The parent skill says get the real thing rather than a description
  of it; here the real thing is prod.
- **Owned.** Either an agent can reach it, or it is founder-gated — and if it is, it is named as
  such on the board immediately, so it never silently stalls the run.

When an item has a measurable half, name it: rows exposed, routes unauthenticated, p99 latency,
error rate at the gate. Taste plus a number beat taste alone; for ship work the number is usually
the whole bar.

## Selection: ship-blocking rank

Before any piece is built, rank the backlog. An item is **ship-blocking** if, with it open, one of
these is true today:

1. A customer's data, money or account access is exposed, lost, or wrongly charged.
2. The product cannot legally or contractually be sold in its market.
3. A paying customer cannot complete the core job the product is bought for.
4. A failure in it is undetectable — no gate, no alarm, no log that would surface it.

Everything else is polish, however visible. Polish is real work and belongs on a gauntlet-loop
board; it does not belong on this one. Rank 1 items go first even when the surface is ugly and the
work is dull. **Do not let the board fill with the pieces that are pleasant to judge.**

Founder-gated items — production migrations, secrets and credential rotation, spend, store or
payment-provider account access — are ranked and boarded like everything else, then marked
`GATED` with the exact action and the exact person. They never block the rest of the board, and
they are handed over as one brief at the end rather than rediscovered one at a time.

## Rungs

Binary throughout, same discipline as the parent — no score is ever assigned.

| Rung | Meaning |
|---|---|
| — | Not started |
| **A** | The gate exists and has been **watched failing** on the live defect. A gate never proven to fire is not a gate |
| **AA** | Fix applied, gate green locally |
| **AAA** | Gate green **in production**, observed by a fresh agent that did not build the fix |
| **AAA+** | At AAA, and a fresh critic cannot name an in-scope way the gate could pass while the defect is still present |

A is the rung that carries the most weight and the one most often skipped. A green check whose
ability to go red was never demonstrated proves nothing — `0 findings` from a broken query looks
exactly like `0 findings` from a clean system. Run the negative control first, watch it go red,
then fix.

AAA+ is the vacuous-verification catch: it asks whether the gate can be satisfied by something
other than the defect being gone. Compose `control-design` when writing the gate, `proof-discipline`
before claiming any rung, and `control-scope` before writing down what a passing check proved.

## Exit, and the stall that is not an exit

The run ends when **every non-gated ship-blocker is AAA+ at the same time**, and the `GATED` list
is handed over as one brief. Not the average. Not most of them.

It does **not** end on a round count, and it does not end because the board looks tidy.

**Stall detection is mandatory.** If a full sweep of the board moves no piece's rung, the run is
stalled, not working. Stop. Do not re-emit the same status in different words. Hand to
`goal-circuit-breaker`, classify the residual, and report what is actually blocking. A loop that
cannot reach its exit will otherwise grind until the session dies, which is how the 2026-08-07 run
ended — mid-grind, claim stale, nothing released.

## Prompt template

Adapt every time. Fill the brackets. Keep the closing lines.

```
Get [PRODUCT] shipped. Work in [REPO] only.

Rank the open work by what actually blocks selling this: customer data, money or access at risk;
cannot legally be sold; a paying customer cannot do the core job; or a failure in it would be
undetectable. Everything else is polish and stays off this board. Anything needing a production
migration, a secret, spend, or store access is founder-gated - board it, mark it GATED with the
exact action and who does it, and move on. It never blocks the rest.

For each item the bar is a gate a hostile auditor could run against production. Binary, no
judge needed, checkable against the live system rather than the repo.

For each item, fan out a builder and a separate critic with fresh context. Before any fix, write
the gate and watch it fail on the live defect - a gate never seen going red is not a gate. Then
fix. Then a fresh agent that did not build the fix confirms the gate green in production. Then a
fresh critic tries to find an in-scope way the gate could pass while the defect is still there.
Only when it cannot is that item done.

The critic should be a harsh critic. Praise is not useful. Never assign a score out of 10; every
judgement is binary.

Do not merge to main or approve a production deploy - those stay human gates.

Keep a live progress page updating as the work evolves so I can watch it. If a full sweep moves
nothing, stop and tell me what is blocking rather than looping.

[LOOP LINE]
```

`[LOOP LINE]` is `/loop on each item until every non-gated blocker is done. Fan out subagents and
ultracode.` for the CLI, and `Keep looping on each item until every non-gated blocker is done. Run
the builders and critics as parallel subagents.` for Desktop.

## What breaks a ship gauntlet

Everything in the parent skill's list, plus:

- **Polishing instead of shipping.** The board fills with surfaces that have nice bars while the
  dangerous items sit unranked. This is the default failure, not an edge case.
- **A gate never watched failing.** Skipping rung A turns the whole board into assertion.
- **Green in the repo read as green in production.** Shipped is not observed. AAA requires prod.
- **Founder-gated items blocking the board.** One item nobody can action holds a run hostage for a
  day. Mark and move.
- **A stall reported as progress.** Re-wording the same blocker across turns is the loop failing,
  and it should exit to `goal-circuit-breaker` rather than continue.
