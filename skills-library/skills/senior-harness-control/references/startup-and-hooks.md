# Senior Harness: startup, hooks and explicit drivers

Moved from the Usage section of SKILL.md. Read before the first mediated tool of a session or when hooks cannot be trusted.

In trusted Pi-Dev-Ops sessions, project lifecycle hooks run the setup driver before mediated local
tools. The first user prompt is frozen byte-for-byte as the primary objective; later prompts are
subordinate until a new task starts. The receipt binds the Git worktree, exact HEAD and dirty-state
digest, this driver, and the installed `senior-harness-control`, `model-router`, and `unlazy` skill folders.
It also executes the provider-neutral router and binds its `RoutingRequest` and `RouteDecision`, then
requires Unlazy as the downstream decomposition, gate, integration, and receipt controller.

For normal Codex and Claude delivery sessions, startup also binds a parallel-first orchestration
policy. Before the root performs implementation, load Unlazy, prove disjoint leaf ownership, admit
the delivery contract, and dispatch the independent leaves up to the four-worker cap. The root owns
coordination and final proof; bounded leaf and integration workers own every mutation. The lifecycle
hook denies root mutation tools throughout a parallel-required session. Grill interactions remain
locked and never receive an early dispatch instruction.

Install the same control stack into all three skill discovery roots with:

```bash
# scripts/install_senior_harness.sh does not exist in this repo (checked 2026-08-29).
cp -R ~/.claude/skills/senior-harness-control ~/.codex/skills/
cp -R ~/.claude/skills/senior-harness-control ~/.agents/skills/
```

This aligns `senior-harness-control`, `model-router`, and `unlazy` under `~/.codex/skills`,
`~/.claude/skills`, and `~/.agents/skills`. Codex and Claude have lifecycle-hook adapters; the
Agents root is discovery-only unless its host separately proves a lifecycle adapter.

Run the same driver explicitly from any Git project when hooks are unavailable or untrusted.
First print the project root, then pass that printed path as `<project-root>`:

```bash
git rev-parse --show-toplevel
```

```bash
python ~/.codex/skills/senior-harness/scripts/setup_driver.py start \
  "<literal request>" --project "<project-root>" --surface codex
```

Use `--surface claude` or `--surface vscode-openrouter` for the other hosts. Exit `0` plus a
`startup-admitted` JSON receipt proves deterministic startup only. It never grants mutation,
business, financial, privacy, deployment, or irreversible authority.

Explicit skill invocation also remains available when automatic triggering is uncertain:

```text
Codex:      $senior-harness <literal request>
Claude:     /senior-harness <literal request>
```

Locate the canonical source, then create the immutable intake envelope from any project:

```bash
python ~/.codex/skills/senior-harness/scripts/senior_harness.py where
python ~/.codex/skills/senior-harness/scripts/senior_harness.py intake "<literal request>" --horizon-required
```

Claude Code uses the same path under `~/.claude/skills/`. Do not assume the active project contains
Pi-Dev-Ops scripts.

Use `--horizon-required` for strategic, architectural, multi-project, product, or repeatedly stalled
work. Omit it for routine bounded work. Exit `0` plus valid JSON is an intake receipt, not execution
proof.

Project hooks cover normal trusted Codex/Claude lifecycle paths. Codex hosted or specialised tools,
Claude `--bare`/`--safe-mode`, disabled or untrusted project hooks, direct shells, and other hosts can
bypass them. Never claim universal interception; use the explicit driver and downstream scheduler
gate on those surfaces.

The hooks mechanically require a valid startup receipt before the first mediated local tool and keep
injecting the frozen objective afterward. In a `/grill-me` or `/grill-with-docs` interaction they
fail closed: only evidence discovery and the Grill state driver may run; edits, pushes, deploys, sends,
and worker dispatch are denied. Outside a Grill, existing host/repository policy still controls generic
mutations. `guard-dispatch` rejects every Grill delivery move until a confirmed shared-understanding
session is supplied and continues rejecting mutating moves until a trusted authority adapter exists.

Recovery is deliberately asymmetric. A missing or invalid session receipt may still admit exact,
read-only discovery tools such as `Read`, `Grep`, `Glob`, `ToolSearch`, web search, and the named
read-only Exa tools, with an explicit zero-authority warning. Mutation, provider, worker, browser
computer-use, send, and deploy tools remain denied. Installed Harness control digests are strict at
startup and the first tool. After a normal delivery session has admitted its first tool, later
Harness-code drift is surfaced as stale-control evidence rather than denying the whole session;
normal host and repository policy still decides generic tools, and a fresh session is required to
produce new control-code evidence. Grill interactions continue revalidating project and control
bytes on every tool, with recovery reads as the only carve-out.

