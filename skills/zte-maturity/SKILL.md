---
name: zte-maturity
description: Zero Touch Engineering maturity model — 4-level assessment with explicit scoring criteria per dimension.
---

# ZTE Maturity Model

## The 4 Levels

### L1 — MANUAL (score 12–20)
Every prompt is typed by a human. Every output is reviewed by a human. The AI is a tool, not an agent.
Characteristics: no specs, no evaluator, no automated triggers, no lessons stored.
Advantage: 2–5x productivity gain over no AI.

### L2 — ASSISTED (score 21–35)
Human writes the spec and reviews the PR. Agent executes the work autonomously.
Characteristics: specs exist, evaluator may exist, some automation, lessons stored but not injected.
Advantage: 10–50x productivity gain.

### L3 — AUTONOMOUS (score 36–48)
System detects work, generates specs from intent, executes, and creates PRs. Human reviews and approves.
Characteristics: evaluator blocking gate, lesson injection, multiple trigger types, session continuity.
Advantage: 50–100x productivity gain.

### L4 — ZERO TOUCH (score 49–60)
System detects, specifies, executes, evaluates, reviews, and deploys. Human sets direction only.
Characteristics: all 12 leverage points at 4–5, automated deployment gate, outcome feedback loop.
Advantage: 100x+ productivity gain.

## Scoring the 12 Leverage Points (1–5 each)

Be strict. Score 5 only when there is clear code evidence of full implementation.

| # | Dimension | Score 5 | Score 3 | Score 1 |
|---|-----------|---------|---------|---------|
| 1 | Spec Quality | Every feature has testable acceptance criteria with context and edge cases | High-level spec only, no acceptance criteria | No spec or vague README |
| 2 | Context Precision | Per-intent context compression, lesson injection, relevant examples always present | Context provided, some noise or irrelevant content | Raw files dumped, no filtering |
| 3 | Model Selection | Auto-selected by task complexity, cost-optimised routing, fallback logic present | Deliberate model choice, some routing | Default model for all tasks |
| 4 | Tool Availability | Full tool suite + custom MCP servers for domain needs | Basic tools only (read/write/bash) | Text generation only, no tools |
| 5 | Feedback Loops | Evaluator critique fed back to generator, lessons stored and injected, multi-turn refinement | Evaluator exists, feedback stored but partial injection | No feedback mechanism |
| 6 | Error Recovery | Retry with backoff, fallback paths, graceful degradation, error classification | Some retries, most errors handled | Crashes on any error |
| 7 | Session Continuity | Phase-level checkpoints, auto-resume from exact failure point, state persisted to disk | Session state saved, manual resume possible | In-memory only, full restart on failure |
| 8 | Quality Gating | Hard blocking gate with minimum score threshold enforced, blocking retry with critique | Gate exists but advisory only | No quality gate |
| 9 | Cost Efficiency | Zero marginal cost architecture, budget tracking per session visible | Moderate cost, no optimisation | High cost per operation, no awareness |
| 10 | Trigger Automation | Multiple trigger types wired: webhook + cron + Linear poller + Telegram | 1–2 automated triggers working | Fully manual, human initiates every run |
| 11 | Knowledge Retention | Lessons stored, analysed weekly, injected into future generator prompts | Lessons stored but not injected or analysed | Nothing retained between sessions |
| 12 | Workflow Standardization | PITER/ADW templates enforced, classifier active, all phases defined, no ad-hoc paths | Informal workflow, some consistency | Ad-hoc, varies by session |
