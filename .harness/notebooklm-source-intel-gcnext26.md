# NotebookLM Source — Intel: Google Cloud Next '26
**Prepared:** 2026-04-19 | **Source ticket:** RA-828 | **Status:** Ready to load (post-conference)
**Conference dates:** 22–24 April 2026 | **Earliest load date:** 25 April 2026

---

## 1. What This Intel Notebook Is

### Purpose

This notebook captures and synthesises announcements from Google Cloud Next '26 that are directly relevant to the Pi-CEO technology stack. It is a one-time intelligence capture, not an ongoing entity knowledge base.

Primary intelligence targets:
- **NotebookLM API** — Is a programmatic API now available? What are the endpoints, rate limits, authentication model, pricing?
- **Gemini model updates** — New versions, context window expansions, pricing changes, availability on Vertex AI
- **MCP / agent frameworks** — Google's official position on Model Context Protocol, any native MCP server SDKs, agent-to-agent protocol announcements
- **Google Workspace AI** — Any features relevant to Pi-CEO's current n8n / NotebookLM workflow (source refresh automation, webhook triggers)
- **Vertex AI changes** — Grounding, function calling, multi-modal updates that affect the RA-830 Gemini evaluation

### Acceptance Criterion

A post-conference intelligence query against this notebook must return a **structured delta report** answering:

> "What did Google Cloud Next '26 announce that changes Pi-CEO's current technology strategy?"

This delta report is the primary input for RA-830 (Gemini Enterprise API evaluation, pending board vote at Sprint 13 / 6 May 2026).

---

## 2. Pre-Conference Context

### Current Pi-CEO Stack (as of April 2026)

| Component | Current tech | What might change |
|-----------|-------------|-------------------|
| LLM backbone | Claude Sonnet 4.6 / Opus 4.7 via `claude_agent_sdk` | Nothing — Agent SDK is Claude-only |
| Long-context pre-processing | Not yet adopted | Gemini Flash viable candidate |
| Knowledge base | NotebookLM (manual source loading) | Programmatic API would enable auto-refresh |
| MCP server | `@modelcontextprotocol/sdk` (Anthropic-originated) | Google MCP adoption changes ecosystem |
| Workflow automation | n8n + manual source uploads | Workspace API triggers would automate freshness |

### Known Pre-Conference Signals

- Google I/O 2025: NotebookLM gained audio overviews and collaborative features. API access was not announced publicly but was hinted at for enterprise customers.
- Google Cloud Next 2025: Gemini 1.5 Pro reached 1M context window. Gemini 2.0 Flash launched for ultra-low-cost pre-processing.
- MCP adoption: Anthropic's MCP spec has been adopted by several third parties. Google's official position (join, fork, or compete) was not declared as of April 2026.
- Agent-to-agent protocol: Google DeepMind published initial work on A2A (agent-to-agent). Formal standards announcement expected.

### What Would Change Pi-CEO's Architecture

**High impact (requires immediate RA-830 update):**
- NotebookLM API general availability with programmatic source upload → eliminates manual n8n workflow, enables Pi-CEO to auto-refresh notebooks after each sprint
- Gemini Flash price drop below $0.05/1M input tokens → changes the cost calculus for pre-processing adoption
- Google official MCP server SDK → reduces maintenance risk vs current community-only MCP tools

**Medium impact (RA-830 board discussion material):**
- Gemini 2.5 Pro with >1M context window at Sonnet-equivalent pricing → direct cost comparison to Claude becomes viable
- Vertex AI native function calling improvements → reduces adapter-layer complexity for any future Gemini integration
- Agent framework SDK parity with `claude_agent_sdk` → opens multi-model agent pipeline possibility

**Low impact (note but don't act):**
- Google Workspace AI features (Docs, Sheets, Gmail AI) → not in Pi-CEO's current architecture
- Google Cloud infrastructure pricing changes → Pi-CEO does not use GCP directly

---

## 3. Sources to Load into NotebookLM (After 25 April 2026)

Load in this order — highest signal-to-noise first:

| Priority | Source | URL / location | What to capture |
|----------|--------|---------------|-----------------|
| 1 | Google Cloud Next '26 keynote transcript | cloud.google.com/blog or rev.com transcript | Full keynote — all product announcements |
| 2 | NotebookLM announcements (blog + session) | notebooklm.google.com or workspaceupdates.googleblog.com | API GA status, new features, pricing |
| 3 | Gemini model announcements | deepmind.google + ai.google.dev | Model versions, pricing, context limits |
| 4 | MCP / A2A session recording | Google Cloud YouTube or session transcript | Google's official agent interop position |
| 5 | Vertex AI updates blog post | cloud.google.com/blog/products/ai-machine-learning | Function calling, grounding, multimodal |
| 6 | Google Workspace Updates blog | workspaceupdates.googleblog.com | NotebookLM Workspace integration updates |
| 7 | This source document | `.harness/notebooklm-source-intel-gcnext26.md` | Pre-conference context and stack state |

**Loading notes:**
- NotebookLM accepts: Google Docs, PDF, web URLs, plain text, YouTube video links
- Use web URL source type where possible (auto-extracts text)
- For YouTube keynote recordings: paste the YouTube URL directly — NotebookLM transcribes automatically
- Max 50 sources per notebook; 7 sources above is well within limit

---

## 4. Acceptance Queries (Run After Loading)

These 8 queries must all return specific, grounded answers (not generic responses) before closing RA-828:

1. **NotebookLM API** — Is a public API available for programmatic source management? If yes, what are the authentication method, rate limits, and pricing tier?
2. **Gemini pricing delta** — What is the updated Gemini Flash price per 1M input tokens announced at GCN26? How does this compare to the April 2026 benchmark ($0.075/1M)?
3. **MCP stance** — What is Google's official position on the Model Context Protocol? Did Google announce an official MCP server SDK or competing standard?
4. **Context window changes** — What is the current maximum context window for Gemini 2.5 Pro and Gemini 2.0 Flash as announced at GCN26?
5. **Agent framework** — Did Google announce a production-ready agent-to-agent (A2A) protocol or SDK? What is the interoperability story with Anthropic's `claude_agent_sdk`?
6. **RA-830 delta** — Based on GCN26 announcements, does the Gemini Flash pre-processing recommendation (from RA-830, completed 2026-04-16) need to be revised? Why or why not?
7. **Workflow automation** — Can Pi-CEO now auto-refresh NotebookLM notebooks programmatically (without manual source uploads)? What would the implementation look like?
8. **Top 3 strategic risks** — What are the top 3 risks that GCN26 announcements introduce to Pi-CEO's current Claude-only architecture?

**Acceptance threshold:** All 8 queries must return specific, grounded answers with source citations. Generic answers (e.g. "Based on the conference…" without specifics) do not count as passing.

---

## 5. Post-Conference Completion Checklist

Run this after 24 April 2026:

- [ ] **Day 0 (25 Apr):** Load all 7 sources listed in Section 3 into a new NotebookLM notebook named `Pi-CEO Intel — Google Cloud Next '26`
- [ ] **Day 0:** Wait for notebook indexing (~10 min after all sources loaded)
- [ ] **Day 0:** Run all 8 acceptance queries (Section 4). Record answers.
- [ ] **Day 0:** Update `.harness/notebooklm-registry.json` — set `id` to the new notebook's ID and `status` to `active`
- [ ] **Day 0:** Update RA-830 description with the delta report from query #6 (RA-830 delta)
- [ ] **Day 0:** Comment on RA-828 with notebook ID + 8-query acceptance test results
- [ ] **Day 0:** Mark RA-828 **Done**
- [ ] **Day 1 (26 Apr):** If NotebookLM API was announced: file new Linear ticket in Pi - Dev -Ops project for `feat(notebooklm): auto-refresh notebook sources via API` (medium priority)
- [ ] **Day 1:** If Gemini pricing changed materially: update RA-830 recommendation section with revised cost analysis

---

## 6. Source References

- `.harness/notebooklm-registry.json` — registry entry: `entity: Intel`, `status: pending_creation`, `linked_issue: RA-828`
- `.harness/RA-830-gemini-evaluation.md` — current Gemini API evaluation (pre-GCN26 baseline). Section 3 "Pricing" and Section 5 "Recommendation" will need post-conference revision if pricing changes materially
- `.harness/notebooklm-entity-template.md` — standard entity onboarding template (this notebook uses a modified intel-capture format, not the entity template)
- RA-830: https://linear.app/unite-group/issue/RA-830 — linked acceptance criterion
- RA-828: https://linear.app/unite-group/issue/RA-828 — parent ticket (this work)
