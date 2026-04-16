# Chinese LLM Breakthrough Patterns for Pi-CEO
**Research date**: 2026-04-14
**Linear tickets created**: RA-930, RA-931, RA-932, RA-933

---

## TOP 5 BREAKTHROUGH TECHNIQUES

### 1. Agentic Training via Executable Task Synthesis (Qwen3-Coder / DeepSeek V3.2)

Qwen3-Coder built a system running 20,000 parallel environments, synthesizing 800K executable tasks. The model engages in multi-turn tool use + execution feedback loops during training itself. DeepSeek V3.2 independently validated this with 1,800+ environments and 85K+ complex instructions.

**Pi-CEO application**: Replicate the data structure. Build harness tasks with verifiable outcomes (CI, test suites, lint gates). Use them to create a corpus of successful agent trajectories for experience replay (→ RA-931).

---

### 2. Structured Reasoning Inside Tool Calls — Cold-Start Seeding (DeepSeek R1 + V3.2)

DeepSeek-R1 format: `<think>...</think><answer>...</answer>`. DeepSeek-V3.2 extended this to be tool-call-aware — the model can reason inside a thinking block, emit a tool call, receive results, and continue reasoning.

**Key insight**: You don't need RL training to get this. **Seed the cold start** with a minimal structural scaffold and the model self-organizes. Template:

```
Before touching any files:
1. What is the full scope of this change?
2. What is the minimal change set?
3. Which tests need updating?
4. What side effects could this have?

Now implement the changes.
```

**Pi-CEO application** (→ RA-932): Prepend structured seeds to generator + evaluator prompts. Toggle with `THINK_SEED_ENABLED=1`. A/B testable via odd/even session IDs.

---

### 3. MoE Architecture / Minimal Tool Set Philosophy (Kimi K2 / Qwen3-Coder)

Kimi K2 (1T params, 32B active) hits 76.8% SWE-bench Verified. Their SWE-bench tool set: `bash`, `createfile`, `insert`, `view`, `strreplace`, `submit` — deliberately minimal.

**Key insight**: 6 orthogonal tools beats 20 overlapping ones. Orthogonality reduces hallucination surface area.

**Pi-CEO application** (→ RA-933): Audit MCP tools for overlap. Run independent read tools in parallel via `Promise.all`. Separate read-only from mutating operations.

---

### 4. A-Mem / Zettelkasten Dynamic Memory Organization

A-Mem (NeurIPS 2025, github.com/WujiangXu/A-mem): treats agent memory as a living knowledge network.
1. When new experience arrives, create structured note with tags and contextual description
2. Scan historical memories for relevant connections
3. Establish bidirectional links based on semantic similarity
4. Allow memories to evolve as contradicting/refining information arrives

**Pi-CEO application** (→ RA-931): After each build run, write an episode note to Supabase `build_episodes`. Use pgvector for similarity retrieval. Only inject verified (tests_passed + outcome=complete) episodes.

---

### 5. Contextual Experience Replay — 51% improvement with no model changes

CER paper (ACL 2025, arxiv 2506.06698): 51% improvement in complex task success with GPT-4o baseline using purely accumulated past experiences in a dynamic context buffer.

AgentRR (arxiv 2505.17716) adds a check function as trust anchor — validates replayed experiences before applying them to new tasks.

**Implementation pattern**:
```python
# After task completion
record_episode(session)  # write to Supabase build_episodes

# Before new task
similar = retrieve_similar_episodes(brief, repo_url, k=3)
# Inject verified episodes as context prefix
```

---

## BEST MEMORY ARCHITECTURE (4-tier)

| Tier | Name | Implementation | What it stores |
|------|------|----------------|----------------|
| 1 | Working Memory | Claude context window | Current task state, active files, recent tool results |
| 2 | Episodic Memory | Graphiti (github.com/getzep/graphiti) | Task run history as temporal facts |
| 3 | Semantic Memory | codebase-memory-mcp (RA-930) | AST structural understanding: functions, calls, imports |
| 4 | Procedural Memory | ReMe (github.com/agentscope-ai/ReMe) | "WHEN [condition] THEN [action]" heuristics extracted from successful runs |

**Storage backend**: Supabase (already in Pi-CEO) + pgvector for embeddings.

---

## PRIORITY IMPLEMENTATION ORDER

1. **Sprint 12 (immediate)**: RA-930 — Install codebase-memory-mcp. Zero code, drop-in MCP config.
2. **Sprint 12**: RA-931 — Experience Recorder. Build the corpus first.
3. **Sprint 13**: RA-932 — Think-block seeds. A/B test against current prompts.
4. **Sprint 13**: RA-933 — Parallel tool execution. Audit + wrap read-only tools.
5. **Sprint 14**: Add Graphiti temporal KG over build_episodes. Graph traversal retrieval.
6. **Sprint 14**: Heuristic extraction via haiku on successful run traces → ReMe-style procedural memory.

---

## REFERENCE TABLE

| Project | Link | Pi-CEO fit |
|---------|------|-----------|
| Graphiti | github.com/getzep/graphiti | Tier 2 episodic memory |
| codebase-memory-mcp | github.com/DeusData/codebase-memory-mcp | Drop-in structural understanding (RA-930) |
| A-Mem | github.com/WujiangXu/A-mem | Memory organization patterns |
| Cognee | github.com/topoteretes/cognee | Full memory stack, Supabase-compatible |
| RLEP | github.com/Kwai-Klear/RLEP | Experience replay reference |
| ReMe | github.com/agentscope-ai/ReMe | Procedural memory / heuristic extraction |
| Code-Review-Graph | github.com/tirth8205/code-review-graph | Claude Code + AST, 6.8x fewer tokens |
| Qwen-Agent | github.com/QwenLM/Qwen-Agent | Parallel tool execution patterns (RA-933) |
| Qwen-Code | github.com/QwenLM/qwen-code | Open Claude Code fork, architecture reference |
| Kimi K2 | github.com/MoonshotAI/Kimi-K2 | Minimal tool set philosophy |
| DeepSeek-R1 | arxiv.org/abs/2501.12948 | Think-block cold-start seeding (RA-932) |
