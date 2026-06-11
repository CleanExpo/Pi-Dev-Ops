# Ruflo Deep Analysis — Strategic Integration with Unite Group / Hermes

**Source:** https://github.com/ruvnet/ruflo.git (v3.5/v3.6)
**Analyzed:** 2026-05-30
**Analyst:** Hermes Agent (Kimi K2.6)
**Scope:** Understand ruflo architecture, extract patterns applicable to Unite Group ecosystem and Hermes Agent

---

## 1. What Ruflo Is

**Ruflo** (formerly Claude Flow) is a multi-agent AI orchestration framework that adds a "nervous system" to Claude Code. It coordinates 100+ specialized agents across machines, teams, and trust boundaries via swarms, self-learning memory, federated comms, and enterprise security.

**By the numbers:**
- 6,000+ commits
- 314 MCP tools
- 16 agent roles + custom types
- 19 AgentDB controllers
- 21 native plugins
- 33 marketplace plugins
- 2,825 core files in v3/

**Two install paths:**
1. **Claude Code Plugin** (lite) — Slash commands + skills + agent defs. Zero files in workspace.
2. **CLI (`npx ruflo init`)** (full) — Complete loop: 98 agents, 60+ commands, 30 skills, MCP server, hooks, daemon.

---

## 2. Core Architecture

```
User --> Ruflo (CLI/MCP) --> Router --> Swarm --> Agents --> Memory --> LLM Providers
                          ^                           |
                          +---- Learning Loop <-------+
```

**Key packages (v3/):**
| Package | Path | Purpose |
|---------|------|---------|
| `@claude-flow/cli` | `v3/@claude-flow/cli/` | CLI entry point (26 commands) |
| `@claude-flow/codex` | `v3/@claude-flow/codex/` | Dual-mode Claude + Codex collaboration |
| `@claude-flow/guidance` | `v3/@claude-flow/guidance/` | Governance control plane |
| `@claude-flow/hooks` | `v3/@claude-flow/hooks/` | 17 hooks + 12 workers |
| `@claude-flow/memory` | `v3/@claude-flow/memory/` | AgentDB + HNSW search |
| `@claude-flow/security` | `v3/@claude-flow/security/` | Input validation, CVE remediation |

---

## 3. Critical Patterns for Unite Group

### 3.1 Dual-Mode Architecture (MOST IMPORTANT)

Ruflo enforces a strict separation:
- **Orchestrator** (Claude Flow) — tracks state, stores memory, coordinates
- **Worker** (Codex) — writes code, runs commands, creates files

**Rule:** Never stop after calling the orchestrator. The worker must immediately continue working.

**Relevance to UG:**
- This is **exactly** what Phill's `nexus-orchestrator` skill already does.
- Ruflo formalizes it with MCP tools: `swarm_init`, `agent_spawn`, `memory_store`.
- **Adoption:** Add MCP-based coordination to Hermes. Instead of just skills, use `memory_store` and `swarm_init` calls.

### 3.2 Skill System

Ruflo skills directory (`.agents/skills/`) contains 100+ SKILL.md files with:
- YAML frontmatter (name, version, description, metadata)
- Markdown body with instructions, patterns, pitfalls
- Optional linked files (references, templates, scripts)

**Sample skill structure:**
```markdown
---
name: agent-swarm-orchestration
version: 1.0.0
description: "Coordinate swarms of agents using topology and strategy"
metadata:
  hermes:
    tags: [swarm, orchestration, multi-agent]
    related_skills: [agent-hierarchical-coordinator, agent-mesh-coordinator]
    pinned: true
---

# Swarm Orchestration

## Patterns
1. Hierarchical: leader + workers
2. Mesh: peer-to-peer
3. Ring: token-passing
...
```

**Relevance to UG:**
- Hermes skills are flatter (no YAML frontmatter, no linked files).
- **Adoption:** Add YAML frontmatter to Hermes skills with: `tags`, `related_skills`, `pinned`, `category`.
- Add `linked_files` support: `references/`, `templates/`, `scripts/` subdirectories per skill.

### 3.3 Memory System — AgentDB with HNSW Vector Search

Ruflo's memory system (`.claude/helpers/intelligence.cjs`) is far more advanced than Hermes's SQLite FTS5:

| Feature | Hermes (current) | Ruflo AgentDB |
|---------|-----------------|---------------|
| Storage | SQLite FTS5 | JSON + HNSW vector index |
| Search | Keyword (AND/OR/phrase) | Semantic vector + keyword hybrid |
| Namespace | Flat (memory, user) | Multi-namespace (patterns, results, context) |
| Learning | None | SONA (Self-Optimizing Neural Architecture) |
| Persistence | Session DB | `.claude-flow/data/` + RVF format |
| Cross-session | No | Yes via `memory persist` |

**Key code pattern (from `intelligence.cjs`):**
```javascript
// Tokenize → TF-IDF-style overlap scoring → rank by confidence
function matchScore(promptWords, entryWords) {
  var entrySet = {};
  for (var i = 0; i < entryWords.length; i++) entrySet[entryWords[i]] = true;
  var overlap = 0;
  for (var j = 0; j < promptWords.length; j++) {
    if (entrySet[promptWords[j]]) overlap++;
  }
  var union = Object.keys(entrySet).length + promptWords.length - overlap;
  return union > 0 ? overlap / union : 0;
}
```

**Relevance to UG:**
- Hermes's FTS5 is keyword-only. It can't find "deployment strategy" when the query is "should we use local servers?"
- **Adoption:** Add vector embeddings to Hermes memory. Use lightweight model (e.g., `sentence-transformers/all-MiniLM-L6-v2`) for embedding.
- Store embeddings alongside session messages for semantic retrieval.

### 3.4 Hook System

Ruflo's hooks (`.claude/helpers/hook-handler.cjs`) automate workflow stages:

| Hook | When Fired | Action |
|------|-----------|--------|
| `pre-task` | Before each agent task | Load relevant memory, set context |
| `post-task` | After each agent task | Store results, update metrics |
| `pre-edit` | Before file edits | Validate changes, check schema |
| `post-edit` | After file edits | Record edit, trigger learning |
| `session-end` | Conversation ends | Consolidate memory, backup |

**Relevance to UG:**
- Phill's `margot_orchestrator_tick.sh` is essentially a manual hook runner.
- **Adoption:** Replace cron-based health checks with hook-based event triggers.
- Example: `post-edit` hook auto-commits `docs/margot/` changes (already doing this manually).

### 3.5 3-Tier Model Routing (COST OPTIMIZATION)

Ruflo routes tasks to the cheapest capable model:

| Tier | Handler | Latency | Cost | Use Cases |
|------|---------|---------|------|-----------|
| **1** | Deterministic codemod | ~1ms | $0 | Structural transforms with **no LLM**: `var-to-const`, `remove-console`, `add-logging` |
| **2** | Haiku | ~500ms | $0.0002 | Simple tasks, low complexity (<30%) |
| **3** | Sonnet/Opus | 2-5s | $0.003-0.015 | Complex reasoning, architecture, security (>30%) |

**Relevance to UG:**
- Phill's agents always use the most expensive model (Kimi K2.6 via OpenRouter).
- **Adoption:** Route simple tasks to cheaper models automatically.
- Example: Health check script → Haiku ($0.02/1K tokens) vs Kimi K2.6 ($0.80/1K tokens) = 40x savings.

### 3.6 Swarm Coordination Patterns

Ruflo supports multiple swarm topologies:

| Topology | Use Case | UG Relevance |
|----------|----------|-------------|
| **Hierarchical** | Leader delegates to specialists | Nexus orchestrator → project agents |
| **Mesh** | Peer-to-peer collaboration | Cross-project coordination |
| **Ring** | Token-passing consensus | Decision-making workflows |
| **Byzantine** | Fault-tolerant consensus | Critical business decisions |
| **Raft** | Leader election, log replication | State machine for operations |

**Relevance to UG:**
- Phill's "swarm of 15+ year Senior Engineers" is conceptually a hierarchical swarm.
- **Adoption:** Use `delegate_task` (Hermes) with swarm topology hints.
- Example: "Spawn 3 agents in parallel (mesh topology) for research, then consensus coordinator to merge."

### 3.7 SPARC Methodology

Ruflo includes a 5-phase development methodology:
1. **Specification** — Define goals, constraints, acceptance criteria
2. **Pseudocode** — Outline algorithm/logic before coding
3. **Architecture** — Design system structure, data flow
4. **Refinement** — Implement with tests, iterate
5. **Completion** — Final review, documentation, deployment

**Relevance to UG:**
- Phill already uses TDD. SPARC adds explicit pseudocode and architecture phases.
- **Adoption:** Add pseudocode requirement to `nexus-engineer` skill before coding.

---

## 4. Ruflo Plugin Marketplace — What's Useful for UG

| Plugin | UG Relevance | Priority |
|--------|-------------|----------|
| **ruflo-core** | Foundation — health checks, plugin discovery | High |
| **ruflo-swarm** | Coordinate multiple agents as a team | High |
| **ruflo-rag-memory** | Smart retrieval — hybrid search, graph hops | High |
| **ruflo-agentdb** | Fast vector database for agent memory | High |
| **ruflo-intelligence** | Agents learn from past successes | Medium |
| **ruflo-adr** | Track architecture decisions | Medium |
| **ruflo-ddd** | Domain-driven design scaffolding | Low |
| **ruflo-sparc** | 5-phase development methodology | Medium |
| **ruflo-security-audit** | CVE scanning, policy gates | Medium |
| **ruflo-jujutsu** | Git diff analysis, risk scoring | Low |
| **ruflo-cost-tracker** | Token usage + budget alerts | High |
| **ruflo-federation** | Cross-machine agent collaboration | Low (for now) |

---

## 5. What to Adopt vs. What to Skip

### ADOPT (High Value, Low Risk)

1. **Skill YAML frontmatter** — Add metadata to Hermes skills (tags, related_skills, pinned, category)
2. **Linked files per skill** — references/, templates/, scripts/ subdirectories
3. **Vector memory search** — Semantic retrieval beats keyword search for complex queries
4. **3-tier model routing** — Route simple tasks to cheap models (massive cost savings)
5. **Hook system** — Replace cron jobs with event-driven hooks
6. **Cost tracking** — Monitor token usage, set budgets, alert on overspend
7. **Memory namespaces** — patterns, results, context (instead of flat memory/user)

### EVALUATE (Medium Value, Medium Risk)

1. **AgentDB HNSW** — Full vector DB is powerful but adds complexity. Start with embeddings in SQLite.
2. **Swarm topologies** — Hierarchical is already used. Mesh/byzantine may be overkill.
3. **SONA learning** — Self-optimizing neural architecture. Cool but unproven at scale.
4. **Federation** — Cross-machine agent collaboration. Useful when UG scales beyond 1 machine.

### SKIP (Low Value or Overkill)

1. **Full ruflo CLI** — Too heavy, custom to ruvnet's workflow. Extract patterns instead.
2. **Flow Nexus platform** — Productized version, not needed for UG.
3. **WASM sandboxed agents** — Premature for current scale.
4. **Byzantine consensus** — Overkill for UG's 1-Board-Member decision structure.
5. **Graph RAG** — Sublinear graph reasoning. Interesting but complex.
6. **Local LLM inference** — ruvllm/Ollama. Not needed while OpenRouter works well.

---

## 6. Immediate Integration Actions

### 6.1 Upgrade Hermes Skills with Ruflo Patterns

Add to existing skills:
```yaml
---
name: nexus-orchestrator
version: 1.1.0
description: "Official Pi-CEO / Margot operating model"
metadata:
  hermes:
    tags: [unite-group, nexus, margot, orchestrator]
    related_skills: [kanban-orchestrator, kanban-worker]
    pinned: true
    category: unite-group-nexus
    adrs: [ADR-001, ADR-026]
linked_files:
  references: [references/nexus-specialised-skills-inventory.md]
---
```

### 6.2 Add Vector Memory to Hermes

Create `~/.hermes/memory-vectors/`:
- Store embeddings alongside session messages
- Use `sentence-transformers/all-MiniLM-L6-v2` (lightweight, 22M params)
- Query: embed prompt → cosine similarity against stored embeddings
- Fallback to FTS5 if vector search returns no results

### 6.3 Implement 3-Tier Model Routing

Add to Hermes config:
```yaml
model_routing:
  tier_1_codemod:  # $0 deterministic
    - var-to-const
    - remove-console
    - add-logging
    - format-document
  tier_2_cheap:    # Haiku / GPT-4o-mini (~$0.0002)
    - health_check
    - status_report
    - simple_summarize
    - data_extraction
  tier_3_expensive: # Kimi K2.6 / Claude Opus (~$0.01)
    - architecture_design
    - security_review
    - strategic_analysis
    - complex_debugging
```

### 6.4 Cost Tracking Dashboard

Track per-project, per-model costs:
```
Daily spend: $12.50
├─ Kimi K2.6: $9.20 (complex tasks: architecture, debugging)
├─ GPT-4o-mini: $2.80 (health checks, summaries)
├─ Codex: $0.50 (code generation)
└─ Potential savings: $4.10 (route 15 tasks from K2.6 to GPT-4o-mini)
```

---

## 7. Ruflo for Phill's Specific Use Case (Voice-to-Action)

The **plaud-processor** system we just built maps directly to ruflo patterns:

| Ruflo Concept | Plaud-Processor Mapping |
|--------------|------------------------|
| Agents | Expert personas (Business Strategist, Technical Architect, etc.) |
| Swarm | Multiple experts analyzing same recording |
| Memory | Plaud recording + transcript + insights stored in DB |
| Hooks | `pre-analysis` (validate signature) → `post-analysis` (deliver insights) |
| MCP tools | AI analysis, webhook delivery, Telegram notification |
| 3-tier routing | Simple transcription → cheap model; Strategic analysis → expensive model |

**Next enhancement:** Add ruflo-style learning:
- After Phill acts on an insight, mark it as "useful" or "not useful"
- Feed this back to the expert's system prompt (reinforcement learning)
- Over time, the expert gets better at predicting what Phill cares about

---

## 8. Competitive Comparison

| Feature | Hermes (current) | Ruflo | Gap |
|---------|-----------------|-------|-----|
| Skills | Flat markdown | YAML + linked files + metadata | Medium |
| Memory | SQLite FTS5 | HNSW vector + graph | Large |
| Model routing | Single model | 3-tier | Large |
| Swarm | `delegate_task` (3 parallel) | 6 topologies, consensus | Medium |
| Hooks | Cron jobs | Event-driven lifecycle hooks | Medium |
| Cost tracking | None | Built-in token budget | Large |
| Learning | None | SONA pattern learning | Large |
| Plugins | Skills folder | 33 marketplace plugins | N/A |

---

## 9. Conclusion & Recommendation

**Ruflo is the most advanced open-source agentic framework available.** It validates many of Phill's existing architectural choices (dual-mode orchestrator, skill system, swarm delegation) while offering clear upgrade paths for memory, cost optimization, and automation.

**Recommended adoption path:**
1. **Week 1:** Upgrade Hermes skills with YAML frontmatter + linked files
2. **Week 2:** Add vector memory search (lightweight embeddings)
3. **Week 3:** Implement 3-tier model routing (test with health checks)
4. **Week 4:** Add cost tracking dashboard
5. **Month 2:** Evaluate ruflo AgentDB for full vector DB replacement
6. **Month 3:** Consider ruflo federation when scaling to multiple machines

**Don't adopt the full ruflo CLI.** Extract patterns. Ruflo is a reference implementation, not a dependency.

---

## Files Referenced

| File | Ruflo Path | Content |
|------|-----------|---------|
| AGENTS.md | `/tmp/ruflo/AGENTS.md` | Agent guide: dual-mode, MCP tools, workflow |
| CLAUDE.md | `/tmp/ruflo/CLAUDE.md` | Full config: 1,181 lines of behavioral rules |
| config.toml | `/tmp/ruflo/.agents/config.toml` | Core settings: model, approval, MCP servers, skills |
| intelligence.cjs | `/tmp/ruflo/.claude/helpers/intelligence.cjs` | Memory layer: init, getContext, recordEdit, consolidate |
| index.md | `/tmp/ruflo/docs/index.md` | Marketplace: 33 plugins, install guide |
| README.md | `/tmp/ruflo/README.md` | Main README: architecture, install, plugins |
