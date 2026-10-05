# fleet-guard

Claude Code mod that keeps subagents and agent-team teammates on allowed models and caps
how many teammates run at once. It hooks `agent.spawn`, which fires before a subagent
starts and, since Claude Code v2.1.289, before a teammate starts (`e.isTeammate === true`).

Linear: RA-7924 · Mods docs: `docs/reference/claude-mods/` (`reference.md` → Subagents)

## Configure (per machine or per session)

| Variable | Value | Unset |
|---|---|---|
| `FLEET_GUARD_MODELS` | Comma list of model ids or aliases, e.g. `sonnet,haiku` | Every model allowed |
| `FLEET_GUARD_MAX_TEAMMATES` | Whole number: the most teammates live at once | No cap |

Both unset → the mod changes nothing.

## What it does

| | |
|---|---|
| **Model rule** (`hooks/fleet.ts` `decide`) | The spawn's model is the one it asked for, or its parent's when it names none (or `inherit`). If that matches no entry, the spawn is rewritten to the **first** entry with `next({ ...e, model })` and one transcript line says so. An entry matches the same id or alias, or an id that has the alias as one of its words (`claude-sonnet-5-5` matches `sonnet`). An alias asked for never matches a full id on the list, because the host decides what an alias resolves to; such a spawn is rewritten to that id. Forks always run on the parent's model and ignore `model`, so they are left alone. |
| **Teammate cap** | Only for teammates. Live teammates are counted with `$.agent.list()`: entries with a `teammateId` whose `status` is `pending`, `running`, `waiting` or `idle`. Idle and waiting teammates count, because they hold their context and wake on a message. `completed`, `failed` and `killed` do not count. At or over the cap the spawn is refused with `fleet-guard: N teammates already running (cap M)`, which Claude reads as the Agent tool's error. Subagents are never capped. |
| **Count unknown** | If `$.agent.list()` fails, the teammate is allowed (never denied blind) and one line says `teammate count unknown`. The model rule still applies. |

Limits: a subagent that names no model is checked against its parent's model. If the
subagent's own definition picks a different model, that model is not seen at `agent.spawn`
(the docs: "undefined lets the agent's own model, then the parent's, decide"). An invalid
`FLEET_GUARD_MAX_TEAMMATES` (not a whole number) logs one line and leaves teammates uncapped.

## Check and test

```bash
claude plugin validate mods/fleet-guard
(cd mods/fleet-guard && claude plugin test)
```

## Install

From the `pi-dev-ops-mods` marketplace in this repository (see `mods/mc-lane/README.md` for
adding the marketplace and turning on auto-update):

```bash
claude plugin install fleet-guard@pi-dev-ops-mods
```

## Try it in one session

```bash
FLEET_GUARD_MODELS=sonnet,haiku FLEET_GUARD_MAX_TEAMMATES=3 claude --plugin-dir mods/fleet-guard
```
