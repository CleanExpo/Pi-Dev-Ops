---
name: leverage-audit
description: 12 Leverage Points diagnostic for agent autonomy — with explicit scoring rubrics and ROI guidance.
---

# 12 Leverage Points Diagnostic

Score each dimension 1–5. The bottom 3 scores (lowest) represent the highest ROI improvements.
Total score determines ZTE level: 12–20 Manual | 21–35 Assisted | 36–48 Autonomous | 49–60 Zero Touch.

## Dimensions

### 1. Spec Quality
Is every feature fully specified with testable acceptance criteria?
- **5** — Acceptance criteria, context, edge cases, and constraints documented for every feature
- **4** — Most features specified, minor gaps
- **3** — High-level spec only, no acceptance criteria
- **2** — Vague brief or README
- **1** — No spec. Prompts are typed ad-hoc.

### 2. Context Precision
Is the right context surfaced at the right time, compressed and noise-free?
- **5** — Per-intent context compression, lesson injection, relevant repo sections always included, noise excluded
- **4** — Context provided, some irrelevant content included
- **3** — Basic context, no compression or relevance filtering
- **2** — Minimal context, mostly raw files
- **1** — No context management. Everything or nothing is provided.

### 3. Model Selection
Is the right model chosen for each task tier?
- **5** — Auto-selected by task complexity (worker/architect/evaluator tiers), cost-optimised, fallback logic
- **4** — Deliberate model choice per task, some routing logic
- **3** — Single model for all tasks
- **2** — Default model with no consideration of alternatives
- **1** — Wrong model for the task being performed

### 4. Tool Availability
Does the agent have every tool it needs without human unblocking?
- **5** — Full tool suite (read/write/bash/git/browser) + custom MCP servers for domain needs
- **4** — Most tools available, minor gaps requiring occasional human input
- **3** — Basic tools only, no domain-specific tooling
- **2** — Limited tools, frequent human unblocking needed
- **1** — No tools. Pure text generation.

### 5. Feedback Loops
Does output quality improve automatically over time without human intervention?
- **5** — Evaluator critique fed back to generator, lessons stored and injected, multi-turn refinement (2–3 cycles)
- **4** — Evaluator exists, feedback stored, partial injection into future prompts
- **3** — Evaluator exists but critique is not looped back to the generator
- **2** — Manual feedback only
- **1** — No feedback mechanism of any kind

### 6. Error Recovery
Does the system recover from failures without human intervention?
- **5** — Retry with exponential backoff, fallback paths, graceful degradation, error classification
- **4** — Retry logic, most errors handled gracefully
- **3** — Basic try/catch, some retries, errors surface to user
- **2** — Errors surface to user with no recovery path
- **1** — Crashes on any error, requires manual restart

### 7. Session Continuity
Can the system resume from exactly where it failed?
- **5** — Phase-level checkpoints, auto-resume from exact failure point, state persisted to disk
- **4** — Session state saved to disk, manual resume possible
- **3** — Session state in memory, lost on process crash
- **2** — Must restart from beginning on any failure
- **1** — No session concept, stateless operation

### 8. Quality Gating
Is there a hard gate that blocks substandard output from shipping?
- **5** — Automated evaluator gate, minimum score threshold enforced, blocking retry with critique injected
- **4** — Gate exists, enforced most of the time, some bypass paths
- **3** — Gate exists but is advisory only, human decides
- **2** — Human review gate only, no automated scoring
- **1** — No quality gate. Anything ships.

### 9. Cost Efficiency
Is the system cost-optimised for its usage pattern?
- **5** — Zero marginal cost architecture, budget tracking visible per session, cost-per-feature tracked
- **4** — Mostly efficient, minor waste, no tracking
- **3** — Moderate cost, no optimisation attempted
- **2** — Expensive per operation, no cost tracking
- **1** — No cost awareness, potential runaway spend

### 10. Trigger Automation
Does work start without human initiation?
- **5** — Multiple trigger types all wired: webhook (GitHub/Linear) + cron + Linear poller + Telegram
- **4** — 2–3 trigger types working reliably
- **3** — 1 automated trigger (cron only or webhook only)
- **2** — Manual only, with automation planned but not implemented
- **1** — Fully manual. Human initiates every single run.

### 11. Knowledge Retention
Does the system get smarter from every run?
- **5** — Lessons stored, analysed weekly, injected into generator prompts for future sessions
- **4** — Lessons stored and sometimes injected into prompts
- **3** — Lessons stored but never surfaced back to the agent
- **2** — Outputs stored but not analysed
- **1** — Nothing is retained between sessions

### 12. Workflow Standardization
Is the end-to-end workflow defined, documented, and enforced?
- **5** — PITER/ADW templates enforced, intent classifier active, all phases defined, zero ad-hoc paths
- **4** — Workflow defined and mostly followed, minor ad-hoc exceptions
- **3** — Informal workflow, some consistency, often improvised
- **2** — Ad-hoc, workflow varies session to session
- **1** — No workflow standard. Every run is different.

## Using This Audit

1. Score each dimension honestly based on what exists in the code, not what is planned
2. Sort ascending — the 3 lowest scores are your highest-ROI targets
3. For each low-scoring dimension, trace back to the specific file or missing file responsible
4. The ZTE level label describes the current state of the system, not its potential
