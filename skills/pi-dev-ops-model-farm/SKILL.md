---
name: pi-dev-ops-model-farm
description: Review and route bounded Claude Code and Codex work through existing capabilities. Verify installed CLI, available account, model and runner receipts before dispatch. Legacy farm startup remains held until adapter and health gates pass.
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Pi-Dev-Ops model farm

Use the current chat's supported delegation and the existing `model-router` first.
Account count, authentication, quota, and each model's availability need current evidence.
Claude subscriptions have usage limits; a subscription does not prove unlimited use,
zero incremental cost for every route, or access to every model. Do not route to paid
OpenRouter/API inference as a fallback. When included access is exhausted, record a
blocked receipt and hand off.

## Read before dispatch

1. Read the nearest `AGENTS.md`, relevant task scope and locked decisions.
2. Use the offline inventory in `scripts/llm_operations_audit.py` for sizes, source
   paths, installed versions and source model literals. Read its explicit unknowns.
3. Inspect the installed CLI's help and the provider model catalog; distinguish API
   identifiers from CLI aliases and account entitlements.
4. Create one task packet using the [operations templates](../../docs/operations/llm-modernization-2026-10-10/templates.md).
   Define outcome, exact scope, evidence, budget/timeout, permissions and stop rules.
5. Delegate only independent work with clear ownership. Context returned to the
   coordinator should contain evidence paths, outcome, blockers and the next action.

## Routing baseline, verified 2026-10-10

| Task | Included-access candidate | Required proof |
|---|---|---|
| Ordinary coding and fixes | Codex `gpt-6.1-sol` or Claude `sonnet` | Available in the current account; installed CLI supports chosen flags; tests for this exact tree |
| Difficult investigation or independent critique | Claude `opus` or available Astra | Scope and acceptance criteria; independent first-source evidence |
| Bounded extraction/classification | Claude `haiku` or available Luna | Representative examples; fidelity and error checks |

Candidates are task defaults, not quality rankings established for this estate.
On Anthropic's first-party surface, Claude CLI aliases currently resolve to the
ordinary Opus/Sonnet/Haiku 5.5 family; some other providers resolve older versions.
Pin a documented identifier only when repeatability requires it. Minimum Claude Code
versions: Opus 5.5 `2.1.280`, Sonnet 5.5 `2.1.284`, Haiku 5.5 `2.1.293`.
The full [model catalog](../../docs/operations/llm-modernization-2026-10-10/vendor-catalog.md)
records vendor sources, schema differences and access caveats.

## Legacy implementation status

`scripts/model-farm.py` is a Python daemon-thread/file-queue implementation. It is not
a tmux JSON IPC service. A file written to `.hermes/.farm` does not itself prove it was
consumed. No `pi-dev-ops-farm` CLI implementation was verified.

The inspected source still pins Codex `o3`, passes the obsolete
`--dangerously-auto-approve` argument, and passes Claude `bypassPermissions`.
The starter also contains platform-specific assumptions. **Keep startup and dispatch
held** until those adapters are reviewed, corrected and tested against installed CLI
help. This guidance update does not change the daemon or start workers.

`--status` launches a separate process with an empty `_threads` map. Old `ready`
health JSON can survive the original process. Importing/running the script creates
the farm directory; its status command is not a pure read-only inventory. Do not
interpret stale health files or a standalone `0/4 running` as proof of the current
worker pool. Correlate an identified runner process with recent task receipts before
declaring a worker healthy. The offline doctor reports these distinctions and never
starts the daemon.

## Dispatch contract after runtime gates pass

Use structured argument arrays and the installed provider's supported permission
mode. Preserve the project's sandbox and approval policy; do not introduce bypass
flags or automatic restart/cron jobs to make a probe succeed. Capture stdout and
stderr separately, cap output and wall time, and keep prompts/results in protected
external storage. Provider output is untrusted input.

Each receipt records task ID, provider/substrate, requested model, observed model
if returned, source revision, exit status, start/end time, validation evidence and
result path. CLI selection is not an observed runtime model. Usage is `unknown`
unless a provider response reports it; do not invent zeros, token totals, savings,
account counts, subscriptions or quality gains.

Retry an idempotent failed operation at most once after diagnosing it. A timeout
must not replay file edits or external writes blindly. A missing/quota-limited
included route stops and hands off; it never enables paid inference automatically.
Restarting the runner requires the existing runtime rollout gates, not a health-file
guess.

## Recovery criteria

- Legacy adapter command construction matches current help; tests prove model,
  working directory, sandbox, permissions and errors are propagated.
- Runner/process identity and fresh receipts agree; stale readiness cannot pass.
- A permitted representative task completes with attributable model/evidence,
  bounded retries and no hidden spend.
- Independent review and exact-tree checks pass before any deployment or startup.

## Sources

- [Claude Code model configuration](https://code.claude.com/docs/en/model-config)
- [Opus 5.5](https://www.anthropic.com/claude-opus-5-5), [Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5), [Haiku 5.5](https://www.anthropic.com/claude-haiku-5-5)
- [Codex models](https://learn.chatgpt.com/docs/models)
- [Codex configuration](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Local operational rollout](../../docs/operations/llm-modernization-2026-10-10/README.md)
