# Frontmatter Schema — the canonical SSOT

The single source of truth for skill frontmatter in `~/.claude/skills/`. Pick the
[`Archetype`](../GLOSSARY.md) first; the fields follow from it. When this file and any skill
disagree, this file wins.

## The three archetypes

| Field | command-skill | agent-role | plain-technique |
|---|:--:|:--:|:--:|
| `name` | ✅ | ✅ | ✅ |
| `description` | human one-line | WHEN-triggers | WHEN-triggers |
| `disable-model-invocation: true` | ✅ | optional | ✗ |
| `argument-hint` | ✅ | optional | ✗ |
| `allowed-tools` | ✅ | ✅ | optional |
| `model` | optional | ✅ | ✗ |

- **command-skill** — a tool the pilot fires deliberately (`judge`, `spm`, `session-handoff`).
  User-invoked: `disable-model-invocation: true`, `description` is a human one-line summary
  (triggers stripped), `argument-hint` present, `allowed-tools` read-only unless it builds.
- **agent-role** — a persona or gate pinned to a model tier (`brand-guardian`, `qa-lead`,
  `pm-core`). `model` pinned; `description` is WHEN-triggers; `allowed-tools` present.
- **plain-technique** — model-invoked know-how the agent reaches autonomously (most
  `marketing-*`, `seo-*`, `video-*`). `description` is WHEN-triggers; no `disable-model-invocation`.

## Field rules

- **`name`** — lowercase-hyphen, matches the folder name. It is the skill's
  [`Leading word`](../GLOSSARY.md); front-load it in the description.
- **`description`** — obeys [`WHEN-not-WHAT`](../GLOSSARY.md). For model-invoked archetypes:
  trigger phrasing ("Use when the user mentions… / asks to…"), one trigger per branch, no
  workflow summary, **no `Model: …` prose**. For user-invoked command-skills: a one-line
  human summary. Every word is context load — prune it harder than the body.
- **`disable-model-invocation: true`** — the one switch that makes a skill user-invoked
  (zero context load). Default to it unless the agent or another skill must reach the skill
  autonomously.
- **`argument-hint`** — only where the skill takes an argument; a literal example in angle
  brackets.
- **`allowed-tools`** — inline comma list (`Read, Grep, Glob, LS, Bash`), not a YAML block
  sequence. Read-only set for any skill that must not mutate. Declare it on any skill that
  takes actions.
- **`model`** — pin only when the tier is load-bearing (agent-role gates). Pin the model ID,
  never bake it into the description.

## Banned fields (remove unless a stated reason is in the body)

`version`, `owner_role`, `status`, `metadata.requires` — one-off divergences with no schema.
A skill that needs lifecycle state belongs in a bucket folder, not a frontmatter field.

## Tool resolution

Never hardcode `mcp__…` prefixes — they are hashed UUIDs that drift. Instruct the skill to
resolve MCP tools by capability via ToolSearch. See `~/.claude/skills/library/connections.md`.

## Canonical examples (copy these)

**command-skill**
```yaml
---
name: session-handoff
description: Record where work stands before stopping, switching terminals, or handing to another agent.
argument-hint: "<ticket, branch, PR, feature, or repo area>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash
---
```

**agent-role**
```yaml
---
name: qa-lead
description: Use when a deliverable needs a pass/fail gate before it ships or merges — code PRs, content, SEO reports, designs.
allowed-tools: Read, Grep, Glob, Bash
model: claude-sonnet-4-6
---
```

**plain-technique**
```yaml
---
name: marketing-copywriter
description: Use when a brief asks for landing-page, ad, email, or blog copy for a portfolio brand.
---
```
