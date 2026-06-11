# Ruflo Integration Plan for Hermes / Unite Group

## Executive Summary

After deep analysis of ruflo (6,647 commits, 323 MCP tools, 33 plugins, 100+ agents), here are the specific patterns to adopt into Hermes — ranked by value and implementation effort.

---

## 1. SKILL SYSTEM UPGRADE (Week 1 — HIGH VALUE)

### Current Hermes Skills
```markdown
# Skill Title

Flat markdown. No metadata. No linked files.
```

### Ruflo Pattern to Adopt
```markdown
---
name: nexus-orchestrator
version: 1.1.0
description: >
  Official Pi-CEO / Margot operating model.
  Use when: planning multi-project orchestration, health checks, ecosystem monitoring.
  Skip when: simple single-file edits, documentation updates.
metadata:
  hermes:
    tags: [unite-group, nexus, margot, orchestrator]
    related_skills: [kanban-orchestrator, kanban-worker]
    pinned: true
    category: unite-group-nexus
    author: phill
    last_updated: 2026-05-30
    adrs: [ADR-001, ADR-026]
    projects: [unite-group, nexus, margot]
linked_files:
  references: [references/nexus-specialised-skills-inventory.md]
  templates: [templates/margot-operating-rules.md]
  scripts: [scripts/margot_orchestrator_tick.sh]
---

# Nexus Orchestrator

## When to Trigger
- Multi-project coordination needed
- Ecosystem health check requested
- Crisis/outage response

## When to Skip
- Single project task
- Simple bug fix
- Code review only
```

### Implementation Steps
1. Add YAML frontmatter parser to `skill_view()`
2. Add `linked_files` support: references/, templates/, scripts/ subdirs
3. Add `tags`, `category`, `pinned`, `related_skills` filtering to `skills_list()`
4. Update all existing skills with frontmatter

---

## 2. VECTOR MEMORY (Week 2 — HIGH VALUE)

### Current: SQLite FTS5 (keyword only)
```sql
SELECT * FROM messages WHERE content MATCH 'deployment strategy'
-- Won't find "should we use local servers?"
```

### Ruflo Pattern: HNSW Vector + Keyword Hybrid
```javascript
// Embed query: "should we use local servers?"
// Vector search finds "Shift RestoreAssist to client-side" (semantic match)
// Fallback to FTS5 if vector search returns no results
```

### Lightweight Implementation for Hermes
Use `sentence-transformers/all-MiniLM-L6-v2` (22M params, ~50MB):

```python
# Add to Hermes session DB
ALTER TABLE messages ADD COLUMN embedding BLOB;

# On query: embed → cosine_similarity → rank
# On store: embed → store alongside message
```

### Cost
- One-time model download: ~50MB
- Per-query: ~50ms on CPU
- Storage: +384 bytes per message (96-dim float32)

---

## 3. 3-TIER MODEL ROUTING (Week 3 — MASSIVE COST SAVINGS)

### Current: Always Kimi K2.6 (~$0.80/1K tokens)

### Ruflo Pattern: Route to cheapest capable model

| Tier | Handler | Cost | Latency | Use for |
|------|---------|------|---------|---------|
| **1** | Deterministic | $0 | ~1ms | var-to-const, remove-console, format |
| **2** | GPT-4o-mini | ~$0.0002 | ~500ms | Health checks, summaries, data extraction |
| **3** | Kimi K2.6 | ~$0.01 | 2-5s | Architecture, security, strategy, debugging |

### Hermes Implementation
```yaml
# ~/.hermes/config.yaml
model_routing:
  health_check: tier_2        # GPT-4o-mini
  status_report: tier_2       # GPT-4o-mini
  simple_summarize: tier_2    # GPT-4o-mini
  architecture_design: tier_3 # Kimi K2.6
  security_review: tier_3     # Kimi K2.6
  strategic_analysis: tier_3  # Kimi K2.6
  complex_debugging: tier_3   # Kimi K2.6
  
tier_1_rules:  # Deterministic codemods (no LLM)
  - pattern: "var-to-const"
    regex: "\\bvar\\b"
    action: "replace with const if not reassigned"
  - pattern: "remove-console"
    regex: "console\\.(log|warn|error)"
    action: "delete line"

tier_2_model: "openai/gpt-4o-mini"
tier_3_model: "moonshotai/kimi-k2.6"
```

### Expected Savings
- Health checks: 20/day × $0.80 → $0.004 = **$16/day → $0.08/day**
- Status reports: 10/day × $0.80 → $0.002 = **$8/day → $0.02/day**
- **Total potential savings: ~$20-30/day (~$600-900/month)**

---

## 4. COST TRACKING (Week 4 — HIGH VALUE)

### Ruflo Pattern: Per-call token tracking + budget alerts

### Hermes Implementation
```yaml
# ~/.hermes/config.yaml
cost_tracking:
  enabled: true
  daily_budget_usd: 50.0
  alert_threshold: 0.8  # Alert at 80% of budget
  
  # Per-project budgets
  project_budgets:
    unite-group: 20.0
    restoreassist: 10.0
    synthex: 5.0
    
  # Per-model costs (per 1K tokens)
  model_costs:
    "openai/gpt-4o-mini": { input: 0.00015, output: 0.0006 }
    "openai/gpt-4o": { input: 0.0025, output: 0.01 }
    "anthropic/claude-sonnet-4": { input: 0.003, output: 0.015 }
    "moonshotai/kimi-k2.6": { input: 0.008, output: 0.08 }
```

### Daily Cost Report (auto-generated)
```
2026-05-30 Daily Spend Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: $12.50 / $50.00 budget (25%)

By Model:
  Kimi K2.6        $9.20  ━━━━━━━━━━━━━━━━ (complex tasks)
  GPT-4o-mini      $2.80  ━━━━━ (health checks, summaries)
  Codex            $0.50  ━ (code generation)

By Project:
  unite-group      $5.50
  restoreassist    $4.20
  synthex          $1.80
  nexus            $1.00

Recommendations:
  ⚠️  15 tasks routed to Kimi K2.6 could use GPT-4o-mini
     Potential savings: $4.10/day
```

---

## 5. HOOK SYSTEM (Month 2 — MEDIUM VALUE)

### Current: Cron-based (`margot_orchestrator_tick.sh`)

### Ruflo Pattern: Event-driven lifecycle hooks

| Hook | When | Action |
|------|------|--------|
| pre-task | Before agent task | Load relevant memory, set context |
| post-task | After task | Store results, update metrics |
| pre-edit | Before file edit | Validate changes |
| post-edit | After file edit | Auto-commit if in docs/margot/ |
| session-end | Conversation ends | Consolidate memory |

### Hermes Implementation
```javascript
// In Hermes gateway
async function runHook(hookName, context) {
  const hooks = await loadHooks();
  for (const hook of hooks[hookName] || []) {
    await hook.execute(context);
  }
}

// Usage:
await runHook('post-edit', { file: 'docs/margot/OPERATING-RULES.md', diff: '...' });
// → Auto-commits if file is in tracked docs directory
```

---

## 6. SECURITY HARDENING (Month 2 — HIGH VALUE)

### Ruflo Patterns to Adopt

| Feature | Ruflo Implementation | Hermes Adoption |
|---------|---------------------|-----------------|
| Input validation | `shell-quote` + regex whitelist | Already using `shell_quote` ✅ |
| Path traversal prevention | Block `../` in file paths | Already in `read_file` ✅ |
| Secret scanning | Block `*_KEY`, `*_SECRET`, `*_TOKEN` in output | Add to terminal output filter |
| CVE scanning | `npm audit` in background worker | Add to health checks |
| Max file size | 10MB limit | Already enforced ✅ |
| Env var filtering | Exclude `LD_PRELOAD`, `NODE_OPTIONS` | Add to `terminal()` env policy |

---

## 7. WHAT TO SKIP (Overkill for UG)

| Ruflo Feature | Why Skip | Alternative |
|--------------|----------|-------------|
| Full ruflo CLI | 2,825 files, too heavy | Extract patterns only |
| Agent federation | Single machine, single org | Not needed yet |
| WASM sandboxed agents | Premature optimization | Node.js child_process is fine |
| Byzantine consensus | 1 Board Member, no distributed consensus | Simple voting/decision log |
| Graph RAG | Complex, unproven at scale | Start with simple vector search |
| Local LLM inference | OpenRouter works well, costs manageable | Evaluate if costs exceed $50/day |
| Flow Nexus platform | Productized version, not needed | Self-hosted Hermes is sufficient |

---

## Implementation Roadmap

### Week 1: Skill System Upgrade
- [ ] Add YAML frontmatter parser to `skill_view()`
- [ ] Add `linked_files` support (references/, templates/, scripts/)
- [ ] Update top 10 skills with frontmatter (nexus-orchestrator, kanban-worker, etc.)
- [ ] Add `skills_list --category` filtering

### Week 2: Vector Memory
- [ ] Add `embedding` column to session DB
- [ ] Integrate `sentence-transformers` model (or use OpenRouter embeddings API)
- [ ] Update `session_search` to use vector + FTS5 hybrid
- [ ] Benchmark: compare keyword vs semantic recall

### Week 3: Model Routing
- [ ] Define tier_1 deterministic rules (codemods)
- [ ] Add `model_routing` to config.yaml
- [ ] Route health checks, summaries to GPT-4o-mini
- [ ] Measure cost savings

### Week 4: Cost Tracking
- [ ] Log every LLM call with token count + model + cost
- [ ] Add `/cost` command to show daily spend
- [ ] Add budget alerts (Telegram at 80%)
- [ ] Weekly cost report

### Month 2: Hooks + Security
- [ ] Implement pre-task, post-task, post-edit hooks
- [ ] Auto-commit docs/margot/ changes
- [ ] Add secret scanning to terminal output
- [ ] Add CVE scanning to health checks

### Month 3: Evaluation
- [ ] Review actual cost savings from model routing
- [ ] Evaluate vector memory recall quality
- [ ] Decide on AgentDB HNSW (full ruflo memory) or stick with lightweight embeddings
- [ ] Evaluate federation if scaling to multiple machines

---

## Expected Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Daily AI cost | ~$30-40 | ~$12-18 | **-60%** |
| Skill discoverability | Manual scan | Filter by tags/category | **+300%** |
| Memory recall | Keyword only | Semantic + keyword | **+150% relevant results** |
| Security posture | Basic | Hardened | **CVE-aware, secret-scanned** |
| Agent coordination | `delegate_task` (3 max) | Hook-based event routing | **Scalable to 10+ concurrent** |

---

## Files

| File | Description |
|------|-------------|
| `brain/strategy/ruflo-deep-analysis-2026-05-30.md` | Full ruflo analysis (15,333 bytes) |
| `brain/strategy/SWAT-deployment-models-2026-05-30.md` | Cloud vs Local analysis |
| `brain/strategy/ruflo-integration-plan-2026-05-30.md` | This document |
