# The Product Factory — Vision, Framework, and Blocks

**The honest version of "one prompt → a complete, sellable product."**

Date: 2026-06-07
For: Phill McGurk
Grounded in: the verified capability registry (`.harness/capabilities/system-capabilities.dod.yaml`), forward-planner, coverage_check, and the SOTA research (`docs/RESEARCH-…`).

---

## The vision, in one line

> One prompt names a product. The system, knowing what it already has, plans it, builds it, designs it, furnishes it, verifies every piece against a real check, and **stages a complete, deploy-ready product for your one go/no-go decision.**

That is achievable as a program of work. The phrase that is *not* honestly achievable — and that has been sold to you before — is "…and sells it on the market, unattended, complete." Here is exactly where the line is, and why drawing it is what makes the rest trustworthy.

---

## The one hard line (read this before anything else)

Your verified capability registry just proved you have 15 of 16 building blocks. So the temptation is to believe the last 1% is "make it fully autonomous to market." It isn't, for two separate reasons, and conflating them is how you've been burned:

1. **Reliability (the research):** the best autonomous build loops complete only ~15–40% of real end-to-end tasks unattended, and the dominant failure is *silent partial success* — looks done, isn't. So a loop that builds *and ships* with no human check will ship broken products confidently. (This is the exact thing Rana catches by hand.)
2. **Wisdom (the nature of selling):** going to market means payments, pricing, legal exposure, real customers, support promises. Those are irreversible, money-and-trust actions. Even at 100% reliability you would not want them fired by a prompt with no human saying "yes, launch this."

So the factory's job ends at **"complete, verified, deploy-ready, staged."** A person says "sell it." That is a design choice, not a missing feature. Everything below is built to make that staged product genuinely trustworthy — so your go/no-go is a real decision, not a leap of faith.

What this buys you that you don't have now: instead of *you* discovering what's missing after being told it's done, the factory tells you the honest completeness number and the exact remaining gaps *before* you decide. Reactive becomes informed.

---

## The missing element, named precisely

You said it yourself: "we have all that built and linked, but we are missing the element that does the Senior PM thinking and uses these assets in combination." The registry confirms it exactly — 15 capabilities present, one red:

> `cap-pm-composes-from-registry` — **a Senior PM that reads the inventory of what the system has and composes those assets into a full product plan.**

You have the tools (116 skills, the swarm, the MCP server, the integrations, the deploy targets, the live backend). You have a planner (forward-planner) and a verifier (coverage_check). What you don't have is the conductor that *knows the orchestra* — that looks at "build me X," looks at what capabilities exist, and writes the score that assigns each part of X to a real, verified capability. That single missing block is the whole gap between "a pile of powerful tools" and "a factory."

---

## The framework — six blocks, what exists, what's missing

```
   ONE PROMPT: "build and stage <product>"
        │
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ BLOCK 1 · CAPABILITY REGISTRY  (the system knows what it has)│  ✅ BUILT
 │ verified self-inventory: 15/16 capabilities proven present   │  (today)
 └───────────────┬─────────────────────────────────────────────┘
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ BLOCK 2 · SENIOR PM COMPOSER  (the missing element)          │  ⛔ MISSING
 │ reads goal + registry + Definition of Done →                 │  (the red line)
 │ a product plan that maps every required step to a REAL,      │
 │ verified capability. forward-planner is its planning engine; │
 │ spm.py / pm_scoper are its seeds.                            │
 └───────────────┬─────────────────────────────────────────────┘
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ BLOCK 3 · CONSTRUCT · DESIGN · FURNISH  (execution)          │  ◐ EXISTS,
 │ the swarm invokes the mapped capabilities to build code,     │   not yet
 │ generate UI, and furnish content/data/assets.               │   composer-driven
 └───────────────┬─────────────────────────────────────────────┘
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ BLOCK 4 · VERIFY  (honest done)                              │  ✅ BUILT
 │ coverage_check gates "done" on executable probes; nothing    │  (today)
 │ is "complete" until its checks pass. UNKNOWN ≠ done.         │
 └───────────────┬─────────────────────────────────────────────┘
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ BLOCK 5 · MARKET-PREP  (stage it)                           │  ○ DRAFTS ONLY
 │ packaging, pricing draft, listing copy, deploy-ready build. │   (autonomous up
 │ Produces proposals, not live actions.                       │   to drafts)
 └───────────────┬─────────────────────────────────────────────┘
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ BLOCK 6 · HUMAN GO/NO-GO  (you)                             │  ◆ BY DESIGN
 │ review the verified completeness + the staged product →      │   human-gated
 │ approve deploy / launch / sell.                             │   forever
 └─────────────────────────────────────────────────────────────┘
```

Legend: ✅ built this week · ◐ exists but not wired to the composer · ○ partial · ⛔ the missing block · ◆ intentionally human.

The shape of the whole thing: **the system already has 5 of the 6 blocks in some form. The factory is one block away** — the composer that turns self-knowledge into a product plan. That is the honest, specific answer to "what am I missing."

---

## How one prompt flows through it

1. You write one prompt: *"Build and stage RestoreAssist's NIR web app."*
2. **Composer** loads the capability registry (what we have) + the project's Definition of Done (what "complete" means) + forward-planner (the 15-move plan). It produces a plan where every move is tagged with the capability that will do it — and flags any move with *no* matching capability as a real gap up front (so you learn what's missing before building, not after).
3. **Swarm** executes the plan — construct (code), design (UI via the dashboard/skills), furnish (content/data) — each builder claiming work single-threaded.
4. **coverage_check** runs continuously; a piece is "done" only when its probe passes. The honest completeness number updates live.
5. **Market-prep** assembles the deploy-ready package + draft pricing/listing.
6. **You** see "RestoreAssist: 94% verified complete, here are the 6% open items and the staged build" → approve or send back.

Nothing claims "done" without a passing check. Nothing reaches the market without you.

---

## Honest sequenced roadmap (what to build, in order)

Each step is real, builds on what exists, and produces something you can run.

1. **✅ Block 1 — Capability Registry.** Done today. The system can prove what it has (`coverage_check` on the capabilities file). Re-run anytime.
2. **Block 2 — Senior PM Composer (the missing element).** Build the component that reads the registry + DoD + runs forward-planner, and emits a product plan with each move mapped to a capability (and unmapped moves flagged as gaps). This is the single highest-value build — it's the thing you're chasing. It reuses forward-planner and `spm.py`.
3. **Wire the loop to coverage** (the earlier red, `ver-loop-coverage-gated`): the build loop may only declare a project done when its DoD probes pass. Closes the original false-completion bug.
4. **Block 3 — composer-driven execution:** have the swarm take the composer's capability-mapped plan and actually run each mapped capability.
5. **Block 5 — Market-prep drafts:** packaging + pricing/listing drafts as proposals.
6. **Block 6 — the Console go/no-go:** surface verified completeness + the staged product in the UNITE-GROUP Console with an approve button. (This is also where "use the Console instead of the terminal" lands.)

Do them in this order. Skipping Block 2 to chase "full autonomy" just rebuilds the false-done machine at larger scale.

---

## The one-line truth

You are not missing tools, vision, or links — you have all of those, now verified. You are missing **one block: the Senior PM that knows what the system has and composes it toward a finished product** — and the discipline to let the factory build-and-stage while a human still says "sell." Build that block on top of the honest verification you now have, and the dream becomes a real, trustworthy machine instead of another confident report.
