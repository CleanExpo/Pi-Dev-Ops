# Vendor baseline, 10 October 2026

These rows were checked against first-party documentation on the stated date.
Provider availability and account entitlement remain separate checks. Desktop/CLI
model names, aliases, effort settings and API request schemas are not interchangeable.
Refresh these sources before a later model rollout.

| Surface | Current documented baseline | Operational caveat |
|---|---|---|
| Claude Opus | `claude-opus-5-5`, released 22 September; Claude Code ≥ `2.1.280` | CLI `opus` is a moving alias; direct API migration needs schema validation |
| Claude Sonnet | `claude-sonnet-5-5`, released 28 September; Claude Code ≥ `2.1.284` | CLI `sonnet` needs current account availability |
| Claude Haiku | `claude-haiku-5-5`, released 7 October; Claude Code ≥ `2.1.293` | CLI `haiku` needs current account availability |
| Claude Fable | Fable 5.1 is a documented gated release from 1 September | Plan credits/access differ; it is not the ordinary default route |
| Codex | `gpt-6.1-sol` ordinary coding; Astra for harder work; Luna for focused work | Verify names in the current Codex catalog and available account |
| OpenAI API | Sol supports `low`, `medium`, `high`, `xhigh`, `max` effort | `none`/`minimal` are unsupported for Sol API; tool calling uses Responses |
| GPT-5.5 | Subscription retirement scheduled for 14 October | API unaffected by that subscription retirement; avoid a blanket deletion |

Sources: [Opus 5.5](https://www.anthropic.com/claude-opus-5-5),
[Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5),
[Haiku 5.5](https://www.anthropic.com/claude-haiku-5-5),
[Claude Code model configuration](https://code.claude.com/docs/en/model-config),
[Codex model catalog](https://learn.chatgpt.com/docs/models),
[Sol model reference](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[OpenAI migration guide](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#migration-quickstart).

Claude Code documents that non-interactive Fable requests can bill usage credits
without a consent prompt when the plan requires credits. Keep that route excluded
until current included-access compatibility is proved.
[Fable usage rules](https://code.claude.com/docs/en/model-config#fable-and-usage-credits)

## Contracts that prevent blind model-name replacements

Opus 5.5 uses adaptive thinking. Existing fixed thinking budgets, temperature,
forced tool choice and assistant prefills require validation against its documented
contract. The estate's `session_sdk.py` currently special-cases adaptive handling
for Fable; updating one registry string cannot prove an Opus migration is safe.
[Opus API migration contract](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide)

Local configuration observed on 10 October: Codex `gpt-6.1-sol` with CLI effort
`ultra`, and Claude `claude-opus-5-5`. This does not authorize copying `ultra` into
a Sol API request. Installed CLIs observed by the coordinator: Claude Code
`2.1.295`, Codex `0.160.1`. Authentication was inspected separately; no account
identity is stored here. Config selection proves neither a successful inference
nor measured output quality.

## Context and evaluation findings

Anthropic's July guidance reports a large reduction of its own system prompt
without measurable loss on its reported coding evaluation. That is evidence for
evaluating smaller instructions; it does not establish a tenfold estate improvement
or authorize removing 80% of Phill's rules.
[Claude context guidance](https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models/)

Anthropic's tool-search research reports reduced tool-definition overhead and
improved accuracy on its benchmark. Dynamic tool search and progressive skill
discovery are existing provider capabilities, so a universal tool-count ceiling
is not a vendor guarantee. Measure actual loaded context in the current session.
[Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use),
[Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

Codex documents an initial skill-catalog budget of at most 2% of the model's context
window, or 8,000 characters when that window is unknown. The actual active window
must be observed. Its default AGENTS instruction budget
is 32 KiB. The doctor's character totals measure installed material, not what the
platform loaded or charged.
[Codex skills](https://learn.chatgpt.com/docs/build-skills),
[AGENTS discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

The Codex MCP server has been removed; experimental app-server is not a production
drop-in replacement. Hosted Evals becomes read-only on 31 October and shuts down
on 30 November. Use the repository's local, versioned fixtures and evidence gates
for this rollout; no paid evaluation service is needed.
[Codex integration status](https://learn.chatgpt.com/docs/mcp-server),
[Evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
