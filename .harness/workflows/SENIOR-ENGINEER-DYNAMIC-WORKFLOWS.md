# Senior Engineer Dynamic Workflows — Claude Code 2.1+ Pattern

**Status:** proposed implementation baseline  
**Source researched:** https://code.claude.com/docs/en/workflows and https://code.claude.com/docs/llms.txt  
**Purpose:** bring a 15+ year senior software engineer operating loop into Pi-Dev-Ops without bloating context, burning tokens, or moving to the next build before the current build is proven.

**Model policy:** use Anthropic/Claude Code workflow patterns as the methodology, but do **not** make Pi-Dev-Ops dependent on external Anthropic API keys. Execution should route through OpenAI-compatible model providers already approved for the system, primarily GPT-5.5-class models and Kimi 2.5-class models.

## Executive read

Pi-Dev-Ops already has the right strategic rail: TAO tiers, Railway/GitHub Actions separation, Linear intake, skill library, smoke-test gates, and autonomous rules. The missing piece is a codified **workflow runtime layer**: repeatable scripts that coordinate many subagents, record evidence, run gates, and stop automatically when a build is not finished.

Anthropic's new Dynamic Workflows pattern fits Pi-Dev-Ops because it converts one-off agent conversation into reusable orchestration. It should not replace TAO. It should sit underneath TAO as the execution method for large codebase work. The implementation should remain provider-agnostic: Claude/Anthropic is the reference pattern, while GPT-5.5 and Kimi 2.5 are the permitted execution models.

## What the Anthropic workflow model adds

Dynamic workflows are JavaScript scripts Claude can write, save, inspect, and rerun. They orchestrate subagents at scale while the main Claude Code session stays responsive.

Use them when:
- one session cannot coordinate enough agents cleanly;
- the task is large enough to justify reusable orchestration;
- outputs need cross-checking by independent agents;
- the build spans many files, repos, or repeated inspections;
- we need a documented loop rather than an ad hoc chat transcript.

Do **not** use them for:
- a single file edit;
- a simple bug fix with one clear failing test;
- tasks better handled by an existing skill;
- destructive migrations or secret/infra changes requiring Phill/Margot/Board approval.

## Pi-Dev-Ops pathway assessment

### Strengths already present

1. **Good strategic topology** — ARCHITECTURE-V2 correctly separates always-on Railway, test-truth GitHub Actions, and human-in-loop Cowork.
2. **Good governance instincts** — autonomous mode has hard stop boundaries around main pushes, PRs, secrets, destructive migrations, and Pi-Dev-Ops self-modification.
3. **Good skill substrate** — skills already cover TAO, token budgeting, closed-loop prompts, agent workflows, review, TDD, security, and ship chain.
4. **Good lifecycle contract** — build-contract.md defines session states and streaming outputs.
5. **Good testing philosophy** — smoke-test gates exist and are mapped by change type.

### Gaps blocking true senior-engineer behaviour

1. **The loop is described, not enforced** — docs say test before moving on, but there is no workflow manifest forcing plan -> implement -> verify -> review -> finalise.
2. **No reusable workflow artifacts** — repeated build patterns are not yet scripts that can be rerun, versioned, and audited.
3. **Subagent use is not bounded by evidence gates** — agents can research/implement/review, but the acceptance contract is not standardized.
4. **Token budgeting is policy, not runtime control** — no manifest declares max agents, max turns, model tier, escalation triggers, or compression points per build type.
5. **Definition of Done is spread across files** — build contract, autonomous playbook, smoke matrix, ship chain, and review rules need one senior-engineer gate document.
6. **No explicit anti-bloat mechanism** — a build can drift into side quests unless the workflow denies out-of-scope files and turns discoveries into follow-up tickets.

## Recommended enhancement

Add a Dynamic Workflow layer with three parts:

1. **Workflow Manifest** — declarative policy for each build: scope, models, agent budget, files allowed, tests required, stop gates.
2. **Senior Engineer Build Loop** — reusable workflow script that runs the build in phases and refuses to advance without evidence.
3. **Definition of Done Gate** — shared acceptance checklist that every workflow writes as machine-readable evidence.

## Senior Engineer Build Loop

Every non-trivial build must pass this loop:

1. **Triage**
   - classify intent: feature, bug, chore, spike, hotfix;
   - identify repo, target files, risk level, required tests;
   - reject vague work or convert it into a plan/ticket.

2. **Context pack**
   - read only the files needed for the task;
   - summarize architecture boundaries;
   - load relevant skills;
   - set max token/agent budget.

3. **Plan gate**
   - produce a minimal implementation plan;
   - list files expected to change;
   - list tests that will prove completion;
   - stop if no verification path exists.

4. **Implementation lane**
   - use one focused agent per lane;
   - no opportunistic refactors;
   - discoveries outside scope become follow-up tickets.

5. **Local verification**
   - run targeted lint/type/test commands;
   - run live/API/browser probe when relevant;
   - collect exact command output.

6. **Independent review**
   - separate reviewer agent checks diff, tests, scope, security, and bloat;
   - reviewer cannot be the same agent that implemented.

7. **Finalisation gate**
   - write evidence file;
   - update Linear/session status;
   - only then move to the next build.

## Provider and model routing

Pi-Dev-Ops should separate **method** from **model**:

- **Method:** Anthropic/Claude Code workflow discipline: dynamic workflows, subagents, scoped plans, evidence gates, independent review, and context compression.
- **Execution providers:** OpenAI-compatible provider layer, not direct external Anthropic API keys.
- **Primary senior reasoning model:** GPT-5.5-class model.
- **Secondary / challenger model:** Kimi 2.5-class model, especially for long-context code review, alternative implementation plans, and cost-controlled cross-checking.
- **Do not hard-code Anthropic-only CLI or SDK assumptions** into Pi-Dev-Ops build contracts. Where Claude Code commands are documented, treat them as reference equivalents and provide OpenAI-compatible execution adapters.

| Phase | Default model | Why |
|---|---|---|
| Triage | Kimi 2.5 or cheaper GPT route | cheap classification |
| Context pack | Kimi 2.5 | long-context retrieval and summarisation |
| Plan | GPT-5.5 | senior judgment |
| Implementation | GPT-5.5 or Kimi 2.5 by repo fit | code execution balance |
| Security / architecture review | GPT-5.5 primary + Kimi 2.5 challenger | expensive only where judgment matters |
| Formatting / docs | cheaper GPT/Kimi route | cheap completion |

Use the most expensive senior model only where judgment matters, not for every token. That is the key cost-control principle.

## Workflow manifest schema

```json
{
  "workflow_id": "string",
  "repo": "string",
  "ticket": "string|null",
  "intent": "feature|bug|chore|spike|hotfix|audit",
  "risk": "low|medium|high|critical",
  "models": {
    "planner": "gpt-5.5",
    "implementer": "gpt-5.5-or-kimi-2.5",
    "reviewer": "gpt-5.5",
    "challenger": "kimi-2.5",
    "worker": "kimi-2.5"
  },
  "budgets": {
    "max_agents": 6,
    "max_turns_per_agent": 8,
    "max_wall_minutes": 60,
    "max_changed_files": 12
  },
  "scope": {
    "allowed_paths": [],
    "denied_paths": [".env", "secrets", "node_modules", ".git"],
    "expected_change_paths": []
  },
  "verification": {
    "required_commands": [],
    "required_live_checks": [],
    "requires_independent_review": true
  },
  "governance": {
    "requires_board_gate": false,
    "allows_push": false,
    "allows_pr": false,
    "allows_secret_change": false
  }
}
```

## Definition of Done evidence

Each workflow run must write an evidence file under `.harness/workflows/runs/<date>-<workflow-id>.md` containing:

- ticket / request;
- repo and branch;
- intended scope;
- actual changed files;
- tests run with exact command output summary;
- reviewer findings;
- unresolved blockers;
- follow-up tickets required;
- final decision: complete, blocked, or rolled back.

## Governance overlay

External-facing outputs, product path changes, customer/client communications, or strategic board artifacts still require CEO Board / Pi governance gate. Dynamic Workflows improve execution; they do not bypass governance.

## Recommended implementation order

1. Add this workflow policy document.
2. Add the `senior-engineer-workflow` skill so Claude Code sessions auto-load the pattern.
3. Add a reusable workflow manifest template.
4. Add a lightweight local validator script that checks a manifest/evidence file exists before finalising.
5. Wire the pattern into future Pi-Dev-Ops build sessions.

## Decision

Recommendation: adopt Dynamic Workflows as Pi-Dev-Ops' **senior engineer execution layer**, not as a separate product. It enhances the current pathway by making senior behaviour enforceable: scoped plans, bounded agents, independent review, real tests, and evidence before progression.
