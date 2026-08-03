# NotebookLM Source — Intel: Google Cloud Next '26

**Prepared:** 19/04/2026 | **Source ticket:** RA-828 | **Status:** Ready to load post-conference
**Conference dates:** 22–24/04/2026 | **Earliest load date:** 25/04/2026

## Purpose

This notebook captures announcements relevant to Pi-CEO: NotebookLM API availability, Gemini model and pricing updates, MCP/A2A interoperability, Google Workspace AI, and Vertex AI changes.

The required post-conference query is: “What did Google Cloud Next '26 announce that changes Pi-CEO's current technology strategy?” The answer must be a structured delta report for RA-830.

## Pre-conference baseline

| Component | Baseline | Change to investigate |
|---|---|---|
| LLM backbone | Claude via `claude_agent_sdk` | Agent SDK or interoperability changes |
| Long-context preprocessing | Not adopted | Gemini Flash price and capability |
| Knowledge base | NotebookLM with manual source loading | Programmatic source API |
| MCP | `@modelcontextprotocol/sdk` | Official Google MCP support |
| Workflow automation | n8n and manual uploads | Workspace API triggers |

## Sources to load

1. Google Cloud Next '26 keynote transcript.
2. NotebookLM announcements blog and session.
3. Gemini announcements from DeepMind and AI for Developers.
4. MCP/A2A session recording.
5. Vertex AI updates.
6. Google Workspace Updates coverage.
7. This pre-conference baseline.

## Acceptance queries

1. Is a public NotebookLM source-management API available, and with what authentication, limits, and pricing?
2. What Gemini Flash pricing changed from the April 2026 baseline?
3. What is Google's official MCP position and SDK support?
4. What are the current Gemini context limits?
5. What production-ready A2A or agent SDK support exists?
6. Does RA-830's Gemini preprocessing recommendation change?
7. Can Pi-CEO now automate NotebookLM source refreshes?
8. What are the top three strategic risks to the Claude-only architecture?

All eight answers must be specific, grounded, and cited before RA-828 is closed.
