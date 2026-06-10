# Pi-Dev-Ops Glossary

Locked definitions for terms used across the Pi-CEO swarm. One paragraph
per term. If a term in this file conflicts with a term in another doc,
this file wins. Authors of new code must align to these definitions
before introducing new variants.

Pattern source: Matt Pocock `sandcastle/CONTEXT.md` — establish a single
root-level glossary so cross-cutting concepts do not drift across
sub-directories. Per `[[board-deliberation-code-patterns-2026-05-15]]`
F4.

---

## agent

A long-running process or invocable function that performs work on
behalf of a user without per-step instruction. Distinguished from a
plain script by autonomy (decides next step), state (maintains context
across invocations), and tool use (calls external services). Examples
in this repo: Margot, Hermes cron jobs, every entry in
`swarm/bots/`, every Linear-claiming worker under
`swarm/pm_core.py`. Used in 16+ Python modules.

## board

The Pi-CEO Board — nine specialist personas (CEO, Revenue, Product
Strategist, Technical Architect, Contrarian, Compounder, Custom Oracle,
Market Strategist, Moonshot) that deliberate a brief and produce a
synthesised decision memo. Implemented in `swarm/board.py` +
`swarm/board/`. Distinct from "board" in a corporate sense — this Board
is an LLM construct. Invoked via `python -m swarm.board` or the
`ceo-board` skill. Outputs land in
`~/2nd Brain/2nd Brain/Wiki/board-deliberation-*.md`. Used in 15+
modules.

## bot

A Telegram-bot row in `public.context_bots`. Each bot has an identity
(BotFather token + username), a routing context
(`linear_team_key` + `linear_project_id`), and a Telegram intake state
(`long_poll_offset`, `intake_enabled`). A bot's identity carries its
routing — zero NLP classification needed. See
`[[project-contextbot-platform]]`. Used in 20+ Python modules.

## cascade

A model-cost-tier ordering applied to LLM calls. Resolves a request
against a sequence of providers ordered cheapest-first, falling through
to the next tier on rate-limit, error, or quality-floor failure. Default
cascade per `[[feedback-model-routing-max-first]]`:
Claude Max (free in-session) → Chinese OS via OpenRouter → Gemini Flash
→ Anthropic API (load-bearing only). Implemented in
`swarm/research_provider.py` and `app/server/provider_router.py`.

## cron

A scheduled job. Two implementations coexist:
(1) macOS LaunchAgents under `~/Library/LaunchAgents/ai.pidev.*.plist`
for local-only periodic work,
(2) GitHub Actions `schedule:` workflows under
`.github/workflows/*.yml` for cloud-running scheduled work. Both are
referred to as "cron jobs" in this repo. The `schedule` skill creates
new cron jobs.

## dispatcher

A function that selects which worker handles an incoming event. Two
distinct dispatchers live in this repo:
(1) `swarm/intent_router.py` routes Telegram messages by content
classification,
(2) `swarm/board/dispatch.py` routes board events to PM personas. The
latter is the gateway between the legacy `[DISPATCH-TO: PM-X]`
sentinel path and the bubus typed-event path (env-flag
`BUBUS_ENABLED`). Used in 6+ modules.

## Hermes

The local-machine cron-runner agent. A user-launched daemon
(`~/.hermes/launchd`) that fires recurring jobs against
`~/.hermes/scripts/*.py`. Distinct from the swarm: Hermes runs on the
operator's host machine; the swarm runs in the Pi-Dev-Ops repo and
deploys to Railway. Hermes feeds the swarm by writing to Supabase
queues (`stripe_provisioning_queue`, `context_bots`, etc.). Used in
6+ swarm modules.

## mandate

A standing authorisation granted by the user (Phill McGurk) that
removes a per-step approval gate. Active mandates: Autonomous Operation
Mandate (2026-04-18, codified in `CLAUDE.md`), Overnight Resume Trigger
(`[[feedback-overnight-resume-trigger]]`). Mandates terminate when the
user retracts them in writing. Not yet in any Python file — purely a
process concept referenced in `CLAUDE.md` and the Brain-1 wiki.

## Margot

The user-facing chat persona that reads the Brain-1 wiki, dispatches to
the Pi-CEO Board for hard decisions, and surfaces decisions back to the
user. Implemented as a Telegram bot + cron-driven research pipeline
(`~/.hermes/scripts/margot-weekly.py`,
`swarm/research_provider.py`). One Margot per founder; not a
class-of-agent. Used in 16+ swarm modules.

## provider

An LLM API endpoint behind a uniform interface. Concrete providers:
`anthropic`, `openrouter`, `gemini`, `ollama`. Each provider exposes a
`generate(prompt, model, ...)` call and a per-call cost record.
Selected by the cascade (see above). Implemented in
`swarm/research_provider.py`, `app/server/provider_router.py`,
`app/server/provider_openrouter.py`. Used in 11+ modules.

## Senior Agent

A higher-cost LLM tier (typically Claude Opus 4.7 or Claude Sonnet 4.7)
reserved for load-bearing or high-stakes tasks: code review, strategy
synthesis, adversarial pressure-test, production-gate decisions.
Distinguished from a plain agent by model tier and per-invocation
budget. Referenced in design docs and the `opus-adversary` skill; not
yet a typed class in code.

## Analyst

The directing intelligence layer for growth-and-sustainability research. Frames
questions, tasks collector skills, grades evidence (NATO/Admiralty), runs ACH /
premortem / gap-scan, and delivers evaluations with kill-switches. Distinct from
collector skills (CMO, CFO, Margot, Scout) which only acquire raw signals.
Implemented as `skills/analyst/SKILL.md`; parent method at
`skills/growth-sustainability-data/SKILL.md`.

## skill

A Markdown-defined workflow under `~/.claude/skills/<name>/SKILL.md`
that Claude Code can invoke. Skills carry a frontmatter `description`
that triggers auto-routing on matching user input. Skills compose with
each other (e.g. `video-director` dispatches to `video-cinematographer`
+ `video-script-writer`). Distinct from an agent: a skill is an
invocable playbook, not a running process. Referenced in 18+ swarm
modules; the canonical registry is the SKILL.md files themselves.

## swarm

The collection of long-running workers and event-driven agents under
the top-level `swarm/` directory. Includes board personas, bots, cron
runners, intake routers, and the meta_curator. Deployed as a single
service to Railway; individual workers are dispatched by LaunchAgents
locally and by GitHub Actions schedules in production. Used in 51+
modules — the most pervasive term in this repo.

## worker

A single-purpose function or class that consumes events from one queue
and produces side effects (DB writes, Telegram sends, Linear ticket
moves). Workers are stateless across invocations — state lives in the
queue or in Supabase. Examples: `provisioner.tick()`,
`intake_router.tick()`, `video_consumer.tick()`. Distinguished from an
agent by scope (one queue, one job) and stateless-ness. Used in 4+
modules.

---

## Notes on under-threshold terms

Per `[[board-deliberation-code-patterns-2026-05-15]]` PR5 spec, every
term used in 3+ swarm Python files should have an entry. `cascade`
(2 files), `Senior Agent` (0 files), and `mandate` (0 files) are
included anyway because they are first-class concepts in the design
docs and the wiki — surfacing them here prevents drift if a future
worker adopts the term in code.
