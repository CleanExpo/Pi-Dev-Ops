# Continuous Agentic Operations — an honest blueprint

**How to run a Senior-PM-led, Kanban-driven, multi-machine loop that always moves projects forward — and the honest line between what can be autonomous and what cannot.**

Date: 2026-06-07
For: Phill McGurk
Grounded in: your actual code (`swarm/pm_scoper.py`, `swarm/kanban_adapter.py`, `swarm/orchestrator.py`, `feature_orchestrator.py`, `fix_orchestrator.py`, `persistent_goals.py`), the false-completion diagnosis, and the state-of-the-art research (both in `docs/`).

---

## 0. Read this first — the honest boundary

You want "a full self-evolving loop, always something happening, go into agentic mode." Half of that is achievable today and half is the exact thing that has been overpromised to you. Being honest about which is which is the whole point.

**Achievable, today, reliably:** a loop that *never stops doing the safe, verifiable work* — researching, planning many moves ahead, detecting gaps, scoping tickets, drafting code in sandboxes, running real checks (tests, type-checks, live smoke tests), and opening pull requests with evidence attached. "Always something moving forward" — yes.

**NOT reliably achievable, and anyone who says otherwise is selling you the thing that burned you:** an unattended loop that *ships production software to market by itself*. The research is blunt — the best autonomous coding loops complete only ~15–40% of real, end-to-end tasks unattended, and the dominant failure is "silent partial success" (green build, dead feature). That is precisely what Rana is catching by hand right now.

So the correct design is not "replace the human gate." It is: **the machines run continuously and do everything up to the point of risk; a human (you or Rana) approves the merge to production.** That keeps things always moving *and* keeps "done" honest. The loop self-improves; it does not self-deregulate.

---

## 1. What Rana is actually using (and its agentic equivalent)

Rana didn't name a tool because the method *is* the tool. What he's doing, in named terms:

| Rana's manual activity | The discipline it is | The automatable equivalent |
|---|---|---|
| Checking screens one by one, testing buttons/forms/uploads | Exploratory + end-to-end (E2E) testing | Playwright / Cypress E2E tests that drive the real UI |
| Validating API responses through the full flow | Integration / contract testing | API contract tests + schema validation; smoke tests against the deploy |
| "Looks done but needs backend validation" | Catching *silent partial success* | An executable acceptance check per requirement (the gap you already started closing) |
| Cleaning up branch changes, reconnecting implementations | Branch reconciliation / integration hygiene | CI on every branch + a merge-readiness gate |
| Testing full user flows, not isolated screens | System testing | Scripted user-journey E2E suites |
| Separate PWA repo for clean deployment | Architecture/repo hygiene | (a human decision — correctly made) |

The honest reading: **Rana is the verification layer your autonomous system lacks.** You can automate large parts of this (E2E + contract + smoke tests become the loop's gate), but until those checks exist and are trusted, a human doing it is not a gap — it's the safety net. The goal is to *encode what Rana checks into automated gates*, so the loop can do the first 80% and Rana reviews the last 20% instead of doing all of it.

---

## 2. What you already have (most of the orchestration is built)

You are much closer than it feels. Real, in-code pieces today:

- **Senior PM** — `swarm/pm_scoper.py`. Picks up under-specified tickets, runs grounded research to produce a concrete spec, posts it to Linear, and flips the label to `agent-ready` so a builder picks it up. Designed to run as a daily LaunchAgent.
- **Builder agents** — `feature_orchestrator.py`, `fix_orchestrator.py`. Claim `agent-ready` tickets and build them in sandboxes.
- **Specialized swarm** — CFO/CMO/CTO/CS bots, `gap_detector.py`, `enhancement_scout.py`.
- **The loop** — `swarm/orchestrator.py`, with shadow mode, kill-switch, and pollers.
- **Kanban** — `swarm/kanban_adapter.py` writes cards to a Hermes-managed SQLite board (`~/.hermes/kanban.db`). **Important honesty:** its own docstring says it does *not* spawn the gateway/daemon/workers — "Hermes's own dispatcher decides whether to claim and run them," and for Pi-CEO use the cards are mostly *visibility markers*. So the board exists; the thing that *executes* cards continuously is the missing part.
- **Long-running goals** — `persistent_goals.py` (your Ralph substrate).
- **Verification seed** — `scripts/coverage_check.py` + `.harness/dod/restoreassist.dod.yaml` (built this week).
- **Planning** — the `forward-planner` skill.
- **Ticket system** — Linear, with the `pi-dev:autonomous` / `agent-ready` / `Ready for Pi-Dev` label contract.

You have the conductor, the musicians, and the sheet music. What's missing is the concert hall that stays open 24/7 and the rule that nobody performs unverified.

---

## 3. What's missing to run continuously, agentically, across two machines

Five gaps, in priority order. Each maps to a real piece of the loop.

**M1 — The verification layer (the most important; you've started it).**
Without executable, project-level Definition-of-Done checks, a continuous loop just produces *false-done at scale* — the nightmare version of your current problem. This is the gate that makes every output trustworthy. You have the seed (`coverage_check.py`); it needs each requirement to carry a runnable probe (a test, an HTTP assertion, a DB assertion). **Until this exists, do not increase autonomy — you'd be automating the lying.**

**M2 — A continuous supervisor on each machine (the "always something happening" part).**
Right now nothing keeps the loop alive 24/7 on your hardware. You need a process supervisor per machine:
- **Mac mini:** a `launchd` LaunchAgent (`~/Library/LaunchAgents/…plist`) that runs the orchestrator/poller and restarts it if it dies. (Your `pm_scoper` docstring already assumes LaunchAgent cron — extend that pattern.)
- **PC:** Windows Task Scheduler (or NSSM to run it as a service) doing the same.
This is what turns "I run it manually" into "it's always running."

**M3 — A shared work queue with atomic claim (so two machines don't collide).**
The moment two machines pull work, you risk both grabbing the same ticket — and two agents writing the same files is the #1 fragility the research warns against (single-threaded writes per unit of work). Linear is your shared queue; what's missing is an **atomic claim**: a builder must move a ticket to an `in-progress:<machine-id>` state *before* starting, and skip anything already claimed. (You already have label/state machinery in Linear; this is a claim convention on top of it.)

**M4 — Output intake with a human merge gate (closing the loop into projects).**
"Import the outputs through to the projects" = the builder opens a **PR with the evidence** (which DoD checks passed, the smoke-test output), CI runs, and *a human approves the merge*. Your `CLAUDE.md` already mandates a "Manual Verification" PR gate — this is enforcing it as the only path from agent work into a project. After merge, `coverage_check` re-runs and the project's verified coverage updates.

**M5 — The PM as a continuous conductor (not just a daily scoper).**
Today the Senior PM scopes ambiguous tickets once a day. To "always have something happening," it needs to be the loop's planner: on a cadence, for each project, run `forward-planner` → diff the plan against `coverage_check` → file the next batch of `agent-ready` tickets so the Kanban is never empty. The PM keeps the board full; the machines keep the board moving; the human keeps the board honest.

---

## 4. The loop, drawn

```
        ┌──────────────────────────────────────────────────────────────┐
        │  SENIOR PM (continuous conductor)                             │
        │  per project, on a cadence:                                   │
        │   forward-planner → define win condition + 15-move plan       │
        │   coverage_check  → what's verified vs missing (the gap)      │
        │   file next batch of `agent-ready` tickets into Linear/Kanban │
        └───────────────┬──────────────────────────────────────────────┘
                        │  board never empty
                        ▼
        ┌──────────────────────────────┐     ┌──────────────────────────────┐
        │  MAC MINI supervisor (launchd)│     │  PC supervisor (Task Sched.)  │
        │  poll → ATOMIC CLAIM a ticket │     │  poll → ATOMIC CLAIM a ticket │
        │  (skip if already claimed)    │     │  (single-threaded per ticket) │
        └───────────────┬───────────────┘     └───────────────┬───────────────┘
                        ▼                                       ▼
        build in sandbox (Ralph loop, hard iter/cost caps, HARD_STOP)
                        │
                        ▼
        RUN THE GATES (the honest oracle):
          typecheck · lint · unit+integration tests · build · live smoke (200) ·
          coverage_check: every DoD probe green?
                        │
              ┌─────────┴─────────┐
        all green                 any red
              │                     │
              ▼                     ▼
     open PR + evidence      back to sandbox (retry, capped) →
              │              if still red: file blocker, move on
              ▼
     ┌───────────────────────────────┐
     │  HUMAN GATE (you / Rana)       │   ← the line autonomy does not cross
     │  review evidence → merge       │
     └───────────────┬───────────────┘
                     ▼
        merged into project → coverage_check re-runs → PM replans
                     │
                     └──────────────► (loop continues, board refilled)
```

Everything above the human gate runs continuously and unattended. The human gate is small, fast, and the reason "done" stays true.

---

## 5. A sensible Mac mini / PC division of labour

Two machines mostly buy you *parallelism across projects* (not across files within one task — that's the fragility trap). A clean default:

- **Mac mini (always-on, the anchor):** runs the Senior PM conductor + the verification/coverage jobs + Apple-only build/test targets (anything needing macOS, e.g. iOS/Safari/PWA testing). It's the machine that's reliably up, so it owns scheduling and the "source of truth" pollers.
- **PC:** runs builder agents for Windows/cross-platform targets and heavier build/test jobs. A second worker drawing from the same Linear queue.
- **Shared spine:** both claim from the *same* Linear board with atomic claims; both write results back as PRs; neither writes to the same ticket at once.

If a machine goes down, the other keeps pulling from the queue — nothing is lost because the queue (Linear), not the machine, holds the state.

---

## 6. What to build first (sequenced, grounded in what exists)

Do not turn on more autonomy before the verification layer exists — that just scales false-done. Order:

1. **Finish M1 — executable verification.** Extend `coverage_check.py` so a DoD requirement can run a real probe (pytest / HTTP / DB). Prove it on one project. *(This is the single highest-value step and builds on what you have.)*
2. **M4 — enforce the PR + evidence + human-merge gate** as the only path from agent work into a project. (Your CLAUDE.md already requires it; make it the wired default.)
3. **M2 — stand up one continuous supervisor** (Mac mini `launchd` first). Get *one* machine running the loop 24/7 on safe work before adding the second.
4. **M3 — add atomic claim** to the builders, then bring the **PC** online as a second worker.
5. **M5 — promote the Senior PM to continuous conductor** (forward-planner → coverage gap → fill the board on a cadence).
6. Only then is "agentic mode" real: the board is always full (PM), always moving (two machines), and always honest (verification + human merge gate).

---

## The one-line answer to "what am I missing?"

Not tools, and not orchestration — you have most of that. You're missing **(1) automated verification that makes "done" mean something, and (2) a process that stays running on your machines and pulls from one shared, claim-safe queue, with a human approving the merge.** Build verification first; everything else is wiring you already mostly own. And keep Rana's gate until the automated gate has earned the trust Rana's manual one currently provides.
