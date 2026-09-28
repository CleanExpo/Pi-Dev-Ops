# Model and plan routing (verified 28 September 2026, Australia/Brisbane)

Standing money rule (10 Sept 2026 decision): no new spending, a $5/day metered ceiling, and
existing subscriptions used to their maximum. This reference orders every lane by that rule.
Every figure below was read from the cited primary page on the research date. Figures marked
(third-party) were not found on a first-party page. Re-verify before relying on any of them;
plans and limits change without notice.

## Lane order

1. **Claude Max subscription** (already paid): planner, coverage reconciliation, workflows,
   headless `claude -p`. Zero marginal cost; the constraint is the 5-hour/weekly limit.
2. **ChatGPT Pro subscription** (already paid): Codex as the *different-model-family* reviewer.
   Zero marginal cost; this is what makes "independent review" independent.
3. **MiniMax M3 API** (metered): bulk read-only discovery over large repositories where 1M
   context matters and the material is not secret. Inside the $5/day ceiling.
4. **TypeSafe Jev API** (metered): typed advisory triage only, per typesafe-planning.md.
   Inside the $5/day ceiling; cost is negligible, egress is the real constraint.

## Claude (Max plan + Claude Code)

| Fact | Source |
|---|---|
| Current lineup: Fable 5.1 ($10/$50 per MTok, 1M ctx, 128K out, adaptive thinking always on, default effort `high`), Opus 5.5 ($4/$20, 1M/128K, always-on thinking, default effort `medium`, cache read $0.20, released 22 Sept 2026), Sonnet 5 ($2/$10, 1M/128K), Haiku 4.5 ($1/$5, 200K/64K). Batch API 50% off. | https://platform.claude.com/docs/en/models/opus-5-5/overview |
| On Max, Fable 5 and 5.1 are a standard part of the plan; up to 50% of the weekly limit may go to Fable, and Fable draws the limit faster than other models. Fable 5.1 needs Claude Code ≥ 2.1.255. | https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan |
| Max = 5x or 20x the Pro allowance depending on tier. | https://support.claude.com/en/articles/11049741-what-is-the-max-plan |
| Agent SDK, `claude -p` and third-party apps still draw from the subscription's usage limits (the announced separate credit was paused 15 June 2026). | https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan |
| Dynamic workflows: JavaScript script Claude writes; `agent()`, `pipeline()`, `parallel()`, `phase()`, `log()`, `args`; schema-validated agent output; 16 concurrent agents by default, 1,000 agents/run cap, 4,096 items per call; `Large workflow` warning at 25 agents or 1.5M projected tokens; saved to `.claude/workflows/` and run as `/<name>`; `Date.now()`/`Math.random()` throw so relaunches are deterministic. Available on all paid plans. | https://code.claude.com/docs/en/workflows |
| `ultracode` = `xhigh` effort + automatic workflow orchestration. The **keyword is inert** from `-p`, the Agent SDK (unless stamped as human input), scheduled tasks and webhooks (v2.1.210+); use `claude --effort ultracode` or the `ultracode` setting for headless runs. Ultracode draws subscription limits faster than `high`. | https://code.claude.com/docs/en/workflows |
| A workflow **pauses at a usage limit only in an interactive session signed in with a claude.ai subscription** with `autoContinueAtUsageLimit` on; in `claude -p`, the SDK, background sessions and agent-team teammates the affected agent **fails** instead. | https://code.claude.com/docs/en/workflows |
| Skill frontmatter: Claude Code accepts `disable-model-invocation`, `argument-hint`, `effort`, `model`, `context: fork`, `agent`, `disallowed-tools`, `hooks`, `paths` etc.; **claude.ai uploads, the Skills API and `package_skill.py` accept only** `name, description, license, compatibility, metadata, allowed-tools` and fail hard on anything else. `allowed-tools` grants permission for one turn; it does not restrict tools. | https://code.claude.com/docs/en/skills |
| `claude plugin eval` (v2.1.269+): each case runs 3× with and 3× without the plugin; graders `regex`, `tool_used`, `tool_order`, `file_exists` (free) and `llm`, `baseline` (judge calls); `--threshold`, `--max-cost-usd`, `--model`, `--judge-model`, `--json`, exit 0/1/2; runs are isolated `claude -p` children with read-only tools unless granted. Counts against plan usage. | https://code.claude.com/docs/en/plugin-evals |
| PreToolUse hooks return `hookSpecificOutput.permissionDecision` of `allow`/`deny`/`ask`; this is the deterministic enforcement layer the skills doc points to ("use hooks to enforce behavior deterministically"). | https://code.claude.com/docs/en/hooks |
| Opus 5.5 became Claude Code's default Opus from v2.1.280 (22 Sept 2026); Anthropic raised five-hour limits at that launch without publishing figures. (third-party) | https://claudelog.com/claude-code-limits/ |

Routing inside Claude:
- Planner/writer: Opus 5.5 at `effort: high` (skill frontmatter). Medium is the model default; a
  planning packet is not routine work.
- Whole-project reconciliation and the final challenge pass: Fable 5.1, budgeted against the
  50% weekly Fable cap. Do not use Fable for fan-out workers.
- Discovery fan-out (file inventories, per-module readers): Sonnet 5 workers inside a dynamic
  workflow, `workflowSizeGuideline` `small` or `medium`; Haiku 4.5 as the eval judge.
- Headless (Pi-Dev-Ops) runs: set effort by flag/setting, never by keyword; expect usage-limit
  failures rather than pauses and design the dispatcher's retry around the reset time.

## OpenAI (ChatGPT Pro + Codex)

| Fact | Source |
|---|---|
| Codex is included across ChatGPT plans; Pro offers 5x or 20x higher rate limits than Plus. Usage across CLI, app, web and IDE draws one allowance; `/status` shows it in the CLI. | https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan and https://learn.chatgpt.com/docs/pricing |
| Recommended models: GPT-6 Astra (most capable), GPT-6 Sol (`gpt-6-sol`, complex coding/agentic), GPT-6 Luna (`gpt-6-luna`, focused repeatable tasks). Non-interactive: `codex exec -m gpt-6-sol "..."`. Ultra mode uses subagents; Luna has no Ultra. | https://learn.chatgpt.com/codex/models |
| **GPT-5.5 retires from Codex with ChatGPT sign-in on 14 October 2026**; GPT-5.4/5.4-mini retired 31 August 2026. Pin `gpt-6-sol` in any saved config now. | https://learn.chatgpt.com/codex/models |
| Restrictive reviewer configuration: `sandbox_mode = "read-only"` with `approval_policy = "on-request"` in `~/.codex/config.toml` (`untrusted` is no longer supported, CLI ≥ 0.149.0). | https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan |
| Codex can point at any provider that supports the Responses API (Chat Completions support deprecated). | https://learn.chatgpt.com/codex/models |
| Pro is $100/month (5x) or $200/month (20x). (third-party) | https://www.morphllm.com/codex-pricing |

Routing: Codex (`gpt-6-sol`, read-only sandbox, `codex exec`) is the cross-model member of the
audit board. It reads the packet and the candidate diff and returns findings; it never edits.
Its receipt is what turns "independent review" from NOT_RUN into a recorded review.

## MiniMax (metered API / Token Plan)

| Fact | Source |
|---|---|
| MiniMax-M3: 1,000,000-token context. Anthropic-compatible base URL `https://api.minimax.io/anthropic` (recommended); OpenAI-compatible `https://api.minimax.io/v1`. Works with the Anthropic SDK via `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`. | https://platform.minimax.io/docs/api-reference/text-anthropic-api |
| Pay-as-you-go, M3 ≤512K input: $0.30 in / $1.20 out / $0.06 cache read per MTok (listed as a permanent 50% discount). >512K input: $0.60 / $2.40. Priority tier = 1.5x. M2.7: $0.30/$1.20. | https://platform.minimax.io/docs/guides/pricing-paygo |
| A Token Plan subscription exists as an alternative to pay-as-you-go. | https://platform.minimax.io/docs/guides/pricing-paygo |

Budget arithmetic at list price: $5/day buys about 16.7M M3 input tokens or 4.2M output
tokens. Use M3 for read-only discovery readers (schemas, route inventories, test lists) over
non-secret repositories, and for first-pass summarisation of large evidence sets. Do not send
credentials, customer data, or anything the credential-exposure remediation classifies as
sensitive. Never let M3 hold the plan: it is a reader, the Max-plan Claude session is the writer.

## TypeSafe Jev (metered API)

| Fact | Source |
|---|---|
| `jev-1.13.0`; aliases `jev-latest`, `jev-preview` (both → 1.13.0 today). Endpoint `POST /v1/systemone`; `GET /v1/models`. Price $0.042 per MTok **input**, output free. Rate limits 250,000 tokens/s and 1,200 requests/min, adjusting dynamically. **Context 64k per request; 32k for `state` plus the longest question.** Text only. Not trained on customer requests; ZDR available for enterprise. | https://docs.typesafe.ai/models |
| Official agent skill install: `claude plugin marketplace add typesafe-ai/skills` then `claude plugin install typesafe@typesafe-ai`; invoke `/typesafe:typesafe-ai`. Other agents: `npx skills add typesafe-ai/skills --skill typesafe-ai`. | https://docs.typesafe.ai/agent-skill |
| Jev is not a coding-agent LLM and cannot replace the model behind Claude Code or Codex; use it for routing, scoring, and true/false checks inside your own code. | https://docs.typesafe.ai/introduction/coding-agents |
| Cookbook "Skill suggestion" picks at most one skill per agent turn from the 182 in Nous Research's Hermes catalog using two requests (rank, then re-check). | https://docs.typesafe.ai/cookbooks/skill_suggestion |

Consequences for the plan: any "evidence relevance" or "requirement compatibility" decision
must be chunked to ≤32k tokens of state, shortlist-first, exactly as typesafe-planning.md
already requires. A 32k-state shadow call costs about $0.0013, so cost never gates a shadow
run; the data-egress classification does. Because the Hermes catalog is the harness's own
upstream kernel, the skill-suggestion cookbook is the reference implementation to evaluate
against the existing skill-selector, not a new design.

## Not verified (do not cite as fact)
- Exact numeric five-hour/weekly quotas for Max 5x/20x and Pro 5x/20x — neither vendor publishes them.
- Whether `claude -p` expands a leading `/plan-to-done` invocation identically to an interactive session.
- Current Library frontmatter schema for the command archetype (private repo not re-read on this date).
- MiniMax Token Plan tier quotas and Codex's per-token credit rate card (both change; read the vendor page at run time).
