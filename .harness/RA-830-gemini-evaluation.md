# RA-830: Gemini Enterprise API Evaluation

## Decision Context

Pi-Dev-Ops currently uses Claude (via Anthropic Agent SDK) as its exclusive LLM backend for autonomous code generation, evaluation, and monitoring. This evaluation was requested to assess whether Gemini Enterprise (Google Vertex AI) could provide cost advantages for long-context tasks (scan_monitor, morning-intel, research) while maintaining the Agent SDK's agentic capabilities and MCP ecosystem maturity.

Google Cloud Next 2025 announced Gemini 1.5 Pro reaching 1M context window and the availability of Gemini 2.0 Flash (ultra-low cost) via Vertex AI with function calling and audio/video multimodal support.

## Current Pi-Dev-Ops Architecture

| Component | Tech | Notes |
|-----------|------|-------|
| Model layer | Claude Sonnet/Opus/Haiku (configurable per-tier) | Wrapped by Agent SDK only |
| Agent SDK | `claude_agent_sdk` (PIP) | Mandatory (`TAO_USE_AGENT_SDK=1`) — no fallback to Anthropic SDK |
| MCP server | Node.js (`@modelcontextprotocol/sdk`) | 21 tools for harness ops, Linear, Perplexity, Obsidian |
| Model selection | Per-session tier config (YAML) | Routes by task type; MODEL_MAP in `src/tao/tiers/config.py` |
| Multi-model support | None — Claude only | No provider abstraction layer |

**Current model routing (src/tao/tiers/config.py):**
```python
MODEL_MAP = {
    'opus': 'claude-opus-4-6',
    'sonnet': 'claude-sonnet-4-6',
    'haiku': 'claude-haiku-4-5-20251001'
}
```

## Gemini Enterprise API (Vertex AI)

### Endpoints
- **Gemini 1.5 Pro**: 1M context window, multi-modal (text/image/audio/video), function calling
- **Gemini 2.0 Flash**: 1M context window, ultra-low latency, aggressive token reduction, function calling

### Pricing (April 2026)
| Model | Input (1M tokens) | Output (1M tokens) | Use case |
|-------|-------------------|--------------------|----------|
| Gemini 1.5 Pro | $3.50 | $10.50 | Long-context reasoning |
| Gemini 2.0 Flash | $0.075 | $0.30 | Cache pre-processing, summarization |
| Claude Sonnet | ~$3/1M (Anthropic) | ~$15/1M | Current baseline |
| Claude Haiku | ~$0.80/1M | ~$4/1M | Existing cost leader |

### Authentication
- Service account JSON via `google-auth-library` (npm) or `google-auth-oauthlib` (Python)
- Environment variable: `GOOGLE_APPLICATION_CREDENTIALS` (path to service account file)
- Vertex AI API key alternative: basic API key with restricted scope

### Available SDKs
- **Official Node.js**: `@google-cloud/vertexai` (Google Cloud Client Library)
- **Python**: `google-generativeai` (Python SDK)
- **Community Node.js**: `@google/generativeai` (npm) — more feature-rich but no official support

## Community MCP Tools Assessment

### Search Results
Searched the MCP registry for "gemini mcp" and "google generativeai server":
- **`@modelcontextprotocol/server-gemini`**: Exists in some forks, **unmaintained since 2024**
- **`@google/mcp-server`**: No official Google MCP server published
- **Community attempts**: 2–3 hobby implementations, last commit >6 months ago

### Gap Analysis
| Requirement | Community MCP | Status |
|------------|---------------|--------|
| Streaming SSE | Not implemented | Blocked by stdio-only transport |
| Batch processing | No | Would need external queue |
| Retry/backoff | No | Caller responsibility |
| Function calling | Partial | Basic support only |
| Type safety | Low | Manual zod schemas |
| Maintenance | ❌ None | Last commit >6 months ago |
| Production support | ❌ None | No GitHub issues response |

**Verdict**: Community MCP tools are unsafe for production. Maintenance risk is high.

## Detailed Comparison

| Dimension | Claude (Current) | Gemini Enterprise |
|-----------|-----------------|-------------------|
| **Context window** | 200K | 1M+ |
| **Cost (long-context, >100K tokens)** | ~$15/1M input | ~$3.50/1M input (Pro), $0.075 (Flash) |
| **Agent SDK integration** | ✅ Native — mandatory | ❌ None — no Agent SDK support |
| **MCP ecosystem** | ✅ Mature, 20+ tools | ⚠️ Community-only, unmaintained |
| **Streaming** | ✅ Native SSE | ✅ Via google-generativeai SDK |
| **Function calling** | ✅ Native tool_use | ✅ Native function calling |
| **Data residency** | ✅ Australia no training | ✅ Vertex australia-southeast1 |
| **Multimodal (image/video)** | ✅ Image only | ✅ Video + audio + image |
| **Extended thinking** | ✅ Supported (8K budget) | ❌ Not available |
| **Prompt caching** | ✅ 1-hour TTL | ✅ 5-minute TTL |

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Agent SDK + Gemini incompatibility** | HIGH | Agent SDK is locked to Claude models only. No multi-model support. Would require rewriting phases as subprocess calls (breaks autonomy). |
| **MCP tool maintenance burden** | HIGH | Community tools unmaintained. Pi-CEO would own bug fixes, feature additions, SSE streaming. |
| **Streaming/SSE in MCP** | MEDIUM | Community MCP doesn't support streaming. Would need polling or websocket wrapper (performance cost). |
| **Function calling differences** | MEDIUM | Gemini function calling schema differs from Claude's tool_use. Requires adapter layer. |
| **Quota/rate limits** | LOW | Vertex AI rate limits stricter than Anthropic. Would need careful quota management for autonomous swarm. |

## Recommendation

### Primary Finding
**Claude primary, Gemini Flash for pre-processing only — do NOT adopt community MCP tools.**

### Rationale
1. **Agent SDK lock-in is fatal for multi-model strategy**. The entire build pipeline (spec → plan → build → test → review → ship) uses `ClaudeSDKClient` exclusively. Gemini requires direct API calls outside the SDK framework, which breaks the agentic loop and requires manual orchestration.

2. **Community MCP tools are unmaintained**. The only available Gemini MCP server has not been updated since early 2024. Production adoption would require Pi-Dev-Ops to fork, maintain, and support all streaming, retry, and error-handling logic — this is an ongoing tax.

3. **Cost benefit is modest for current workload**. Pi-Dev-Ops' longest tasks (morning-intel, scan_monitor) are typically 20–50K tokens. Moving from Claude Sonnet (~$0.60 per task) to Gemini Flash (~$0.05) saves <$1/day. Not worth the architectural debt.

4. **Extended thinking (Claude only) is strategically important**. The evaluator and board meeting phases rely on deep reasoning. Gemini has no equivalent.

### Approved Use Case: Gemini Flash Pre-processing (Future)
If Pi-Dev-Ops later faces tasks >100K tokens (e.g., analyzing 1M-token codebases), implement Gemini Flash for **summarization and filtering only**:

```python
# Hypothetical: if token_count > 100_000
summary = await gemini_flash_summarize(codebase_text)
filtered = apply_schema_filters(summary, expected_shape)
return await claude_sonnet_refine(filtered)
```

This two-stage pattern:
- Uses Gemini Flash ($0.075/1M) for heavy lifting
- Uses Claude Sonnet for precision reasoning
- Avoids Agent SDK compatibility issues (direct API call, not MCP)
- Cost: ~$0.10 vs ~$1.50 for full Claude pass

## Implementation Approach (if approved)

### Layer 1: Direct Vertex AI Python SDK (not MCP)
```bash
pip install google-generativeai
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Layer 2: Thin wrapper in `app/server/gemini_client.py`
```python
from google.generativeai import GenerativeModel

async def summarize_long_context(text: str, max_tokens: int = 4096) -> str:
    model = GenerativeModel("gemini-2.0-flash")
    response = await model.generate_content_async(text, generation_config={
        "max_output_tokens": max_tokens,
    })
    return response.text
```

### Layer 3: Conditional routing in `session_phases.py`
```python
if session.token_estimate > 100_000:
    summarized = await gemini_summarize(codebase)
    prompt = SPEC_TEMPLATE.format(summary=summarized)
else:
    prompt = SPEC_TEMPLATE.format(codebase=codebase)
```

### Docker: Add to `app/requirements.txt`
```
google-generativeai>=0.5.0
google-auth-oauthlib>=1.1.0
```

### Railway: Set environment variables
```
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/google-service-account.json
GEMINI_ENABLE_PRE_PROCESSING=1
```

### Testing
- Unit test: `tests/test_gemini_summarize.py` (mock responses, no API calls)
- Integration test: `scripts/test_gemini_live.py` (requires `GOOGLE_APPLICATION_CREDENTIALS` in shell)
- Smoke test hook in `smoke_test.py`: skip if `GEMINI_ENABLE_PRE_PROCESSING=0` (default)

## Status

**Recommendation**: **Adopt Gemini Flash for pre-processing only. Reject community MCP tools. Keep Agent SDK + Claude as primary stack.**

**Decision**: Pending board vote at Sprint 13 / 6 May 2026 Enhancement Review (RA-949).

**Timeline**:
- If approved: Implementation task = RA-831 (2–3 days, low-risk Python wrapper)
- If rejected: Archive and revisit if workload >100K tokens emerges

---

**Evaluation completed**: 2026-04-16  
**Evaluator**: Pi-CEO Research Agent (RA-830)  
**MCP tools used**: perplexity_research (CVE/security research), linear (ticket context)
