---
name: boardroom
description: Multi-model triangulation for high-stakes decisions. Fan out 2–4 panellists, score divergence via Jaccard, synthesise one answer. Use for architecture, strategy, or machine spec pipeline board review — not routine single-model tasks.
owner_role: Orchestrator
status: active
automation: manual
---

# boardroom — multi-model triangulation

Programmatic API: `app.server.spec_pipeline.boardroom.boardroom_query`.

See ADR 007 (`adrs/007-machine-ship-gate.md`) for machine ship integration.

## When to invoke

- High-stakes outputs where wrong call cost exceeds extra panellist cost
- Machine spec pipeline stage after `/spm` spec is drafted
- User asks "what does the boardroom think"

## When NOT to invoke

- Routine routing — use single-model intent matrix
- More than 4 panellists

## Output contract

Returns `answer`, `panel` (verbatim per model), `min_pairwise_similarity`, `escalated`, `decision`, `confidence`.

## Default panel (OpenRouter)

- Panellists: `deepseek/deepseek-v4-flash`, `anthropic/claude-sonnet-5`
- Synthesiser: `anthropic/claude-sonnet-5`
- Escalation (Jaccard &lt; 0.35): `anthropic/claude-opus-4-8`

## Hard rules

- Never skip synthesis — concatenate-only is banned
- Never swallow panellist responses
- Survive panellist failures (`asyncio.gather` with exceptions)


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Ingest the high-stakes question. (2) Classify the domain: architecture, security, marketing, financial, product. (3) Query the Portfolio Registry for relevant project context. (4) Identify the decision cost (wrong answer > 1 hour rework → qualifies).

**Orient:** (1) Select the domain-appropriate panel composition (see MOA Panel Defaults reference). (2) Determine if this is a triangulation (2-4 panellists) or a full boardroom (5-7 panellists with CEO loop). (3) Set the Jaccard threshold (default 0.35; security-critical → 0.50). (4) Pre-select the synthesiser and escalation model.

**Decide:** (1) Fan out to all panellists in parallel (max 3 concurrent via delegate_task). (2) Collect verbatim outputs. (3) Extract key claims per panellist. (4) Score pairwise Jaccard similarity.

**Act:** (1) If min_similarity < threshold → escalate to stronger model. (2) Synthesise the unified answer, preserving panellist verbatim sections. (3) Emit confidence score + decision + divergence map. (4) Lock the panel composition for audit.

### 2. OpenAI Structured Output Schema

```json
{
  "version": "3.1",
  "question": "...",
  "domain": "architecture | security | marketing | financial | product",
  "panel": [{"skill": "", "model": "", "output_hash": "", "output": ""}],
  "synthesiser": {"skill": "", "model": ""},
  "key_claims_matrix": [{"claim": "", "panellists_supporting": [], "panellists_opposing": []}],
  "jaccard_scores": [{"pair": ["", ""], "similarity": 0.0}],
  "min_pairwise_similarity": 0.0,
  "escalated": false,
  "escalation_reason": "",
  "unified_answer": "",
  "decision": "go | no-go | escrow | escalate",
  "confidence": 0.0,
  "panel_divergence_map": [{"area": "", "divergence": "high | medium | low"}],
  "lock_hash": "sha256"
}
```

### 3. Multi-Tool Selection Matrix

| Decision type | Panel composition |
|---------------|-------------------|
| "Should we ship?" | storm + judge + spm + security-audit |
| "Which architecture?" | cto + storm + security-audit + judge |
| "Is this secure?" | security-audit + storm + tao-judge |
| "Go to market?" | cmo-growth + cfo + marketing-orchestrator + judge |
| "Budget approval?" | cfo + ceo-mode + cto + judge |
| "Autonomous mission?" | tao-loop + tao-judge + nexus + session-handoff |

### 4. Self-Critique Loop

After synthesis:
- Did I preserve every panellist's verbatim output? (banned: swallowing)
- Did I score Jaccard on the KEY CLAIMS, not on full text? (important)
- Is the unified answer a genuine synthesis or a weak average? (check for "neither A nor B" copouts)
- If confidence < 0.7, is escalation justified?
- Self-score: synthesis quality (0.3), claim preservation (0.3), Jaccard correctness (0.2), escalation appropriateness (0.2). Total < 8 → manual review.

### 5. Safety & Guardrails

- Never concatenate-only — synthesise or escalate; never dump.
- Survive panellist failures: if 1 of 4 fails, proceed with 3; if 2 of 4 fail, abort and report.
- No hallucinated panel composition: always verify skills exist before dispatch.
- CEO gate: boardroom output is always external-aware; flag client-facing implications.

### 6. Performance Optimisation

- Parallel dispatch: use delegate_task with batch (tasks array) for concurrent panellists.
- Claim pre-extraction: ask panellists to output KEY CLAIMS as a structured list to speed Jaccard scoring.
- Caching: cache Portfolio Registry context across all panellists to avoid redundant reads.

### 7. Error Recovery

- Panellist failure → retry once; if still failing, exclude and note.
- Delegate batch timeout → split into individual dispatches.
- Jaccard calculation error → fall back to manual summary comparison.

### 8. Cross-Model Fallbacks

| Primary | Default panellist | Synthesiser | Escalation |
|---------|-------------------|-------------|------------|
| OpenRouter multi-model | `deepseek-v4-flash` | `claude-sonnet-5` | `claude-opus-4-8` |
| Claude-only | `claude-sonnet-5` | `claude-sonnet-5` | `claude-opus-4-8` |
| Cost-sensitive | `claude-haiku-4` | `claude-sonnet-5` | `claude-sonnet-5` |

### 9. Observability

Emit: question, domain, panel size, panellists used, failed count, min_jaccard, escalated, final_decision, confidence, duration, tokens used per panellist.

### 10. Multi-Modal Awareness

- Ingest architecture diagrams from each panellist → visual consensus scoring.
- Ingest UI mockups → aesthetic divergence map.
- Output boardroom minutes as PPTX for board review, or Slack blocks for team digest.
