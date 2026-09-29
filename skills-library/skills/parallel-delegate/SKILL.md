---
name: parallel-delegate
description: Split work across multiple Claude subagents running concurrently when a task has independent subtasks. Use when you'd otherwise do N sequential round-trips, when independent codebase areas need exploring at once, or when a long-running investigation can be parallelized. Fires multiple Agent tool calls in a single message so they actually run in parallel, not serially.
---

# Parallel subagent delegation

Most slowdown in agent work comes from *serial round-trips that didn't need to be serial*. This skill is the discipline of recognising when work is independent and dispatching it concurrently.

The key mechanic: **multiple `Agent` tool calls in a single message run in parallel.** Sequential `Agent` calls in separate messages run serially. Always batch.

## When to invoke

Strong fit:
- Exploring 2+ unrelated areas of a codebase ("how does auth work?" + "how does billing work?")
- Researching N options before deciding (compare 3 libraries, evaluate 3 approaches)
- Reviewing a change from N angles (security + performance + a11y + types)
- Verifying a fix lands correctly in N services / N repos
- Long-running investigations with no shared state

Poor fit:
- Steps that genuinely depend on each other (don't parallelize a chain)
- Tasks that need the same files (will conflict on edits — keep serial)
- Trivial single-file lookups (just `Read` directly)
- When the user is waiting and total wallclock is short anyway

## Decision rule

Ask: "If subagents A and B run at the same time, does A's result change what I'd ask B?" If **no**, parallelize. If **yes**, sequential.

## How to dispatch

Send one message containing multiple `Agent` tool uses. Each agent gets:
- A specific, narrow scope (one question, one area)
- The right `subagent_type` for its work — `Explore` for research, `Plan` for design, `general-purpose` for everything else, specialised types when they fit
- Its own `model` if relevant (e.g., one Opus for adversarial review while others run on Sonnet)
- A self-contained prompt — agents don't see this conversation

Example shape (conceptual, not a literal call):

```
[Agent A]   subagent_type=Explore     prompt="trace the auth flow from login to session"
[Agent B]   subagent_type=Explore     prompt="trace the billing flow from cart to charge"
[Agent C]   subagent_type=general     prompt="check what tests exist for these flows"
```

All three in **one** message. They run concurrently; you get three results back to synthesize.

## Picking the right subagent type

| Need | Subagent | Why |
|---|---|---|
| Codebase research, "how does X work" | `Explore` | Optimised for fast file/symbol search |
| Implementation strategy / architecture | `Plan` | Designs step-by-step plans |
| Open-ended task with edits possible | `general-purpose` | Has all tools |
| Adversarial design review | `general-purpose` + `model: "opus"` | See `opus-adversary` skill |
| React/TSX quality | `vercel:react-best-practices` | Specialist |
| Ship readiness audit | `general-purpose` | Cross-cutting |

## Synthesizing results

Don't just concatenate agent outputs. Read them, find the points of agreement and disagreement, resolve conflicts, then report a single coherent answer to the user. Agents see fragments; your job is the whole picture.

## Pairing with other skills

- **opus-adversary**: spawn the Opus reviewer in the same message as the implementation-verification agents, so review and verification happen concurrently.
- **adversarial-review**: do **not** parallelize Codex calls — Plus quota is too tight to spam multiple at once.

## Anti-patterns

- ❌ Spawning 8+ agents "to be safe" — if you don't have specific questions for each, you don't need them.
- ❌ Vague prompts ("look around and tell me what you find") — narrow each agent's scope or you get vague output.
- ❌ Parallelizing edits to the same file — last write wins, work is lost.
- ❌ Forgetting the agent has no context — every prompt must be self-contained.
