---
name: context-cockpit
description: Inspect loaded context, instruction conflicts, tools and output quality before a prompt or model migration.
argument-hint: "[task or symptom]"
disable-model-invocation: true
allowed-tools: Read, Bash
---

# Context cockpit

Use the current task and actual loaded context to choose a bounded improvement. Current official sources: [Claude context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [Claude skills](https://code.claude.com/docs/en/skills), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-advanced). Recheck these before a migration.

1. Inspect the native context view and relevant global/ancestor/project/local instructions, auto-loaded rules, memory, plugins and tool output. Record actual measurements where available; label character-based token estimates. Identify duplication, conflicts and obsolete model compensation. Preserve user intent, business/brand facts, authority, privacy, spending limits and acceptance criteria.
2. Inspect native tool discovery before disabling anything. Modern Claude/Codex can defer tool definitions; MCP does not necessarily load every schema at startup. Choose relevant tools and bounded outputs using supported client settings. There is no universal fifty-tool limit, three-server limit or percent at which quality is proven to drop. Keep useful access available; do not install a second CLI or disable a working service by habit.
3. For ongoing work, save a small revision/evidence checkpoint and use native compact when context pressure affects the task. Use clear/new chat for an unrelated task only when the user/workflow calls for it. Do not clear active objectives or opaque compaction state.
4. Select effort/model within the task's capability, privacy and verifier floors. Defaults, CLI aliases, pinned API IDs and account entitlement are separate observations. Never start below the quality floor, assume unlimited subscription capacity, or silently cross to paid/API fallback. Use current model-router and installed client probes.
5. Run a representative before/after comparison in fresh sessions at the same model/effort. Measure task success, completeness, rework, latency and tokens where exposed. A smaller input is a context saving; a better result requires outcome evidence. Read [operating procedures](references/operating-procedures.md) for checkpoints, release interactions and model/schema caveats.

For a failing MCP, inspect its actual error, package/configuration and documented credential resolver. Do not paste keys into chat or report absence from a partial search. Diagnose and repair within authorized scope, with a rollback and a direct readback.

Historical adoption notes are in [the September record](references/anthropic-adoption-20260923.md), and dated release incidents in [the August-September incident record](references/release-incidents-202608-09.md); they do not establish today's model capabilities or account state. This skill is advisory and grants no release, credential, spend or deployment authority.
