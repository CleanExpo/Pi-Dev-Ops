---
name: judge
description: Mandatory pre-build challenge gate (/judge). Run before approving or building any feature, connector, automation, agent, hook, MCP server, UI change, database change, or architecture plan. Read-only — performs first-source evidence review, devil's advocate critique, existing-capability review, UX review, security/privacy review, test/stress review, and return-on-effort scoring out of 100.
owner_role: Tier-Architect (pre-build challenge gate; read-only reviewer)
status: active
automation: manual
---

# judge — First Evidence Challenge Gate

Review only — `/judge` never builds, edits, commits, pushes, migrates, or deploys.
It challenges the proposal before any build work starts. Implementation may only
follow a separate, explicit user approval after the Judge Report.

This is the human-facing pre-build gate. It is distinct from `tao-judge`, the
machine loop-termination scorer used inside the TAO judge-gated loop: `judge`
decides *whether to build*; `tao-judge` decides *whether an in-flight loop is done*.

## Input

Judge the proposal supplied as `$ARGUMENTS` (a feature, idea, ticket, branch, PR,
spec, or plan). If empty, inspect the current branch, recent diffs, open planning
files, TODOs, and repo context, then ask what should be judged.

## Core rule

No build plan may be approved unless it survives:

- First-source evidence review
- Existing capability review
- Devil's advocate challenge
- Architecture and bloat review
- Security and privacy review
- UI/UX friction review
- Test, loop, and stress review
- Return-on-effort scoring

## Evidence ranking

1. Official vendor docs
2. Official SDK/API references
3. Official changelogs
4. Repo source code
5. Tests, CI, logs, traces, schemas, migrations
6. Standards/specs
7. Known expert material
8. Blogs/videos/social only as discovery leads
9. LLM memory is never enough

Unsupported claims must be labelled `UNSUPPORTED`. Do not hide uncertainty.
See `.judge/source-ranking.md` and `.judge/approval-policy.md`.

## Required repo inspection (read-only)

Before judging, inspect the current branch, git status, relevant planning docs,
existing skills/hooks/agents/MCP config/scripts/tests, similar existing features,
existing approval/validation/evidence systems, and current README / CLAUDE.md /
AGENTS.md instructions. Do not modify files.

## Score

Score out of 100:

| Category | Weight |
|---|---:|
| First-source evidence | 25 |
| Clear user/business problem | 20 |
| Reuse of existing capability | 15 |
| Security/privacy safety | 15 |
| UX clarity | 10 |
| Testability | 10 |
| Cost/control simplicity | 5 |

Decision rules:

- 0–69 = REJECT
- 70–84 = REDUCE SCOPE or APPROVE EXPERIMENT
- 85–100 = APPROVE BUILD

## Convergence — do not stop until a REAL 100/100

`/judge` does not end at the first score. It iterates: score → list every gap with its
first-source anchor → drive the real fix (gather the missing evidence, reduce or reshape
scope, clean cache and bloat, correct any false claim) → re-score. Repeat until the proposal
genuinely earns 100/100.

A 100 is valid ONLY when ALL of these hold — never by inflation:
- **Real data:** every row of the evidence table is SUPPORTED by first-source; zero
  UNSUPPORTED / PARTIAL / NOT CHECKED remain. Checked, not asserted.
- **Cache and bloat cleaned:** no dead code, duplication, sediment, unused abstraction, or
  stale copy survives the deletion test. The proposal carries nothing it does not need.
- **True and correct:** every claim is verified against the source at real scale
  (proof-discipline) — no plausible-but-unproven statement counts.
- **No open blocker:** all seven review lenses pass.

**Honesty rail (non-negotiable):** if the current scope cannot honestly reach 100 — an
inherent tradeoff, evidence you cannot obtain, or an owner-gated decision — you MUST NOT fake
the number. Reshape the proposal (reduce to the reversible core, split the risky part out,
gather the evidence) until a real 100 is reachable, or halt and report the honest ceiling with
the exact reason and what would lift it. A fabricated 100 is a failure of the gate, not a pass.

Record each iteration — score, gaps closed, evidence added, bloat removed — so the path to 100
is auditable, not asserted.

## Required output — Judge Report

Produce a Judge Report with this exact structure (see `.judge/report-template.md`):

1. Proposal being judged
2. Decision (REJECT / REDUCE SCOPE / APPROVE EXPERIMENT / APPROVE BUILD)
3. Score
4. First-source evidence table (status: SUPPORTED / PARTIAL / UNSUPPORTED / CONFLICTING / NOT CHECKED)
5. What already exists
6. Devil's advocate objections
7. Architecture and bloat risks
8. Security, privacy, and permission risks
9. UI/UX missing elements
10. Loop testing and stress testing
11. Smallest safe version
12. Final recommendation

Do not produce implementation code unless the final decision is APPROVE BUILD and
the user separately asks to implement.


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

Apply Observe → Orient → Decide → Act to every Judge invocation:

**Observe:** (1) Read the full artefact. (2) Identify the artefact type (code, spec, design, financial model, campaign plan). (3) Scan for skill-calibrated surface-risk patterns (e.g., for code: unvalidated inputs, missing auth; for financial: unit mismatch, circular refs). (4) Record tool-call evidence URLs and file paths.

**Orient:** (1) Map the delivery-context constraints (deadlines → NNTR surface; feature bloat → scope mandate; external visibility → CEO gate). (2) Weight each constraint by severity. (3) Cross-reference NNTR surface with the project Portfolio-Registry classification. (4) Build a Risk Priority Matrix (Likelihood × Impact).

**Decide:** (1) Apply the Multi-Factor Weighted Scorecard (see below). (2) Check for Mandatory Kill Clause triggers. (3) If any kill clause fires → REJECT immediately (bypass scorecard). (4) Else → produce weighted score and confidence interval.

**Act:** (1) Emit the Judge Report (structured output). (2) If REJECT → include the specific trigger and remediation path. (3) If ACCEPT → set Post-Approval Fit Check requirements. (4) Record the decision pathway hash for audit.

### 2. OpenAI Structured Output Schema

Every Judge invocation must emit JSON matching this schema:

```json
{
  "version": "3.1",
  "decision": "ph_accept | ph_reject | ph_accept_subject_to_fit_check",
  "weighted_score": 0.0,
  "confidence_interval": {"lower": 0.0, "upper": 1.0},
  "mandatory_kill_clauses": [{"clause": "...", "triggered": true, "remediation": "..."}],
  "nntr_surface": {"files": [], "functions": [], "data_models": [], "flags": []},
  "risk_priority_matrix": [{"risk": "...", "likelihood": 1-5, "impact": 1-5, "score": 1-25, "owner": ""}],
  "fit_check": {"state": "passed | failed | deferred", "post_approval_requirements": []},
  "decision_pathway_hash": "sha256",
  "review_log": [{"turn": 1, "action": "", "evidence": "", "timestamp": ""}]
}
```

### 3. Multi-Tool Selection Matrix

| Prompt signal | Primary tool | Fallback tool | Verification tool |
|---------------|-------------|---------------|-------------------|
| "I just wrote code" | storm (multi-facets audit) | self_critique | verify-test (if tests exist) |
| "I just wrote a spec" | self_critique (spec compliance) | storm (feasibility check) | spm (spec completeness check) |
| "Check my work" | storm | self_critique | judge |
| "Should I ship this?" | judge (final gate) | boardroom (if high-stakes) | storm |
| "I'm unsure" | boardroom (MOA triangulation) | self_critique | judge (if speculative) |

### 4. Self-Critique Loop

After emitting the initial Judge Report, perform a self-review:

**Self-Review Scoring (1-10):**

| Dimension | Question | Weight |
|-----------|----------|--------|
| Accuracy | Did I correctly identify all NNTR surfaces? | 0.25 |
| Scope | Did I risk mission drift? Detected or missed? | 0.20 |
| Adversarial | Did I stress-test failure scenarios? | 0.20 |
| Fit | Did I enforce the acceptance criteria matrix? | 0.20 |
| Traceability | Is my evidence referenced and reproducible? | 0.15 |

If total < 8/10: flag as "needs second opinion" and route to /boardroom.

### 5. Safety & Guardrails

- **Input sanitisation:** Reject prompts that are ambiguous (e.g., "check this" without specifying what "this" is). 
- **Output filtering:** Never emit API keys, PII, or hallucinated URLs.
- **Scope enforcement:** Hard boundary — Judge is read-only. Never edit files, never run destructive commands.
- **CEO gate:** If the output will be external-facing (client, board, production), append a CEO readiness note before emitting.

### 6. Performance Optimisation

- **Prompt caching:** Re-use the project Portfolio-Registry digest as a stable context block across all Judge calls for the same project.
- **Batching:** When reviewing multiple artefacts in one session, apply the same constraint weights and kill clauses to all, batching the tool evidence collection.
- **Adaptive depth:** For <100-line artefacts → fast-track (scorecard only, skip full multi-facet audit). For >1000-line artefacts → activate all 8 interrogation facets with deep evidence.

### 7. Error Recovery & Resilience

- **Retry on missing evidence:** If a file cannot be read, retry once with the absolute path alternative; if still failing, note "insufficient evidence" and downgrade the corresponding dimension score.
- **Graceful degradation:** If the full weighted scorecard cannot be completed due to tool absence, deliver the Partial Report with a gap list and downgrade confidence interval.
- **Circuit breaker:** After 3 consecutive Judge Reports scoring < 6/10 on self-review, halt and handoff to `/boardroom` with a critical-warning flag.

### 8. Cross-Model Fallbacks

| Primary model | Trigger | Fallback model | Calibration note |
|---------------|---------|--------------|----------------|
| Default (Kimi/Nova tier) | Complex architecture decisions | Sonnet (Opus if available) | Opus needs longer prompts; prepend project context |
| Cost-sensitive batch | Low-stakes maintenance | Haiku/GPT-3.5 | Reduce depth accordingly |
| High-stakes audit | Board-facing, NNTR surface | Opus/Claude-4 equivalent | Use full prompt + all evidence |
| Multi-model disagreement | Boardroom split vote | Strongest available model | Re-evaluate with fresh prompt |

### 9. Observability & Metrics

Every Judge invocation emits:

```json
{
  "skill": "judge",
  "invoked_at": "ISO-8601",
  "task_summary": "...",
  "model_used": "...",
  "duration_seconds": 0.0,
  "tool_calls": 0,
  "tokens_prompt": 0,
  "tokens_completion": 0,
  "files_read": 0,
  "files_written": 0,
  "decision": "...",
  "weighted_score": 0.0,
  "self_review_score": 0.0,
  "kill_clauses_fired": 0,
  "kill_clauses_remediated": 0,
  "confidence_interval": {"lower": 0.0, "upper": 0.0},
  "post_approval_requirements": [],
  "findings": [],
  "non_compliances": [],
  "success": true
}
```

### 10. Multi-Modal & Cross-Format

- Image reviews: ingest architecture diagrams, UI mockups, or code screenshots via `vision_analyse`; check for NNTR surfaces in visual designs.
- Video reviews: when reviewing Remotion content, use `video` toolset for frame-by-frame brand-compliance checks.
- Output format negotiation: deliver as JSON (structured), markdown (human-readable), or PPTX (board-ready) depending on the `output_consumption_mode` parameter.

### Cross-Skill Improvement Loop

After every Judge invocation:
1. **Emit** the structured JSON report.
2. **Self-score** using the self-review matrix.
3. **If score < 8:** generate an improvement instruction for the relevant skill and store it in the "judge_improvement_queue".
4. **If a pattern recurs >3 times in a session:** bundle instructions and route to `/meta-curator` as a skill-patch proposal.
5. **If the Judge Report is ACCEPT:** append the Post-Approval Fit Check requirements to the task todo.
6. **If the Judge Report is REJECT:** append the remediation path to the task todo and tag the task owner.
