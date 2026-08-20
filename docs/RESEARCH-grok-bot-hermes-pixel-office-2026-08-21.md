# Grok Bot and pixel-office references for the Nexus visual agent harness

**Date:** 2026-08-21

**Scope:** Primary-source research identifying the products behind the user's “Grok Bot” and “Hermes Pixel Table” references. This note distinguishes the products, records their actual visual/state models, and extracts lessons for the proposed non-coder product factory. It does not recommend adopting their code or licences without a separate review.

## Executive conclusion

The user is combining two complementary ideas:

1. **Grok Bot** is the conversational team metaphor: named, always-on AI teammates, each given a job, with multi-bot chats, handoffs, persistent working context, computer use, and approval requests.
2. **Hermes Pixel Office** is the visible-work metaphor: every running agent or subagent becomes a pixel character whose location, animation, and alert state reveal whether it is working, researching, waiting, blocked, or finished.

The proposed Nexus product should combine those ideas but add the missing trust layer:

> A founder talks to a named AI product team, watches the team work in a visual studio, and sees each claimed result backed by gates, evidence, cost, ownership, and an exact deliverable.

The pixel office should not be decorative telemetry. It should be a human-readable projection of the same authoritative job and evidence state used by the orchestrator.

---

## 1. Exact reference: Grok Bot

- First-party launch: [Introducing Grok Bot](https://x.ai/news/introducing-grok-bot), published 2026-08-11.
- First-party launch video: [Grok Bot product film](https://media.x.ai/v1/website/260810_2245_bw_dr_cursor_bot_edit_v8-60724aba.mp4).

SpaceXAI describes Grok Bot as a team of always-on agents that work inside ordinary apps and continue after the user leaves. The launch page says users can message a Bot like a colleague, teach routines through demonstration, run several Bots in parallel, put them in group chats, and use a manager or chief-of-staff Bot above specialists. Bots can pass work and request human judgment when required.

The first-party video shows the product primarily as a **named teammate roster plus chat/work feed**, available from desktop and phone. Bots have memorable names and job identities; their messages report concrete work landing in tools such as Slack, Gmail, and Notion. It is not a pixel office.

### Useful lessons

- **Start with people-language, not orchestration-language.** A founder should create “Research Lead” or “Product Engineer,” not configure a graph node.
- **Conversation is the command surface.** The system can build formal goals, scope, ownership, and gates in the background.
- **Names and roles make delegation legible.** Every Bot needs a stable identity, description, remit, current assignment, and escalation rules.
- **Mobile continuity is part of the product.** A founder can assign work, inspect evidence, and approve a gate without returning to a desktop.
- **Handoffs should be visible.** The user should see which specialist produced an input, who accepted it, and what evidence crossed the boundary.
- **Routine learning should be explicit and reviewable.** A successful workflow can become a reusable skill only after the user can inspect and approve the resulting procedure.

### Important boundary to clarify

The launch page uses both “Bots have their own computer” and “Bots share a computer of their own in the cloud.” It does not clearly define on that page whether isolation is per Bot, per user, or per team. Nexus should not inherit this ambiguity: every project and agent view should expose its workspace, credentials, permissions, and isolation boundary.

---

## 2. Exact reference: Hermes Pixel Office

The closest match to “Hermes Pixel Table” is **Hermes Pixel Office**, created by Teknium for Hermes Agent:

- Repository: [`teknium1/hermes-pixel-office`](https://github.com/teknium1/hermes-pixel-office)
- Reviewed head: [`64a2b63b6eaf71c2388d65d2bf71f240c0a52705`](https://github.com/teknium1/hermes-pixel-office/tree/64a2b63b6eaf71c2388d65d2bf71f240c0a52705)
- Licence: MIT.

The project makes every Hermes session and delegated subagent an animated pixel character. Agents walk in, sit at desks, animate according to tool activity, flag approvals with a red alert, and leave when the session ends. Delegated subagents use gold collars and goal labels. It can run in a browser or a VS Code panel.

The implementation is deliberately **visual-only**. Hermes lifecycle hooks append events; a local service folds them into current state; a canvas office polls and renders the snapshot. The plugin does not block or control the agent. See the [feature and architecture description](https://github.com/teknium1/hermes-pixel-office/blob/64a2b63b6eaf71c2388d65d2bf71f240c0a52705/README.md#what-youll-see).

### What the visual metaphor actually communicates

| Visual | Operational meaning |
|---|---|
| Character enters and sits at a desk | A real session has started |
| Typing / reading / browsing / terminal animation | The current tool category |
| Gold collar and goal label | A delegated subagent and its purpose |
| Red `!`, “needs input,” and waiting counter | Human approval is blocking progress |
| Character walks out | The session ended |
| Shared room | One glance across all local Hermes processes |

### Useful lessons

- **Make invisible concurrency glanceable.** A user should not need to read terminal logs to know whether five agents are active or stalled.
- **Blocked work must be louder than busy work.** Approval and failure indicators should dominate animation.
- **Render lifecycle events, not guesses, whenever possible.** The office must reflect authoritative events from the harness.
- **Keep observation separate from control.** The visual layer can fail without corrupting the job; consequential controls still need authenticated, auditable commands.
- **Show parent-child relationships.** A subagent is not merely another worker; its parent, remit, and handoff should be visible.

---

## 3. Related projects that sharpen the idea

### Pixel Agents — likely the original visual lineage

- Repository: [`pixel-agents-hq/pixel-agents`](https://github.com/pixel-agents-hq/pixel-agents)
- Reviewed head: [`3537e140c2094761beae748592aeb92ece8edfdd`](https://github.com/pixel-agents-hq/pixel-agents/tree/3537e140c2094761beae748592aeb92ece8edfdd)
- Licence: MIT.

Pixel Agents renders terminal agents as animated office characters in VS Code or a standalone browser. It shows live activity, permission waits, subagents, persistent teammates, workspace areas, and editable layouts. Its stated direction is especially close to the user's vision: agent-agnostic adapters, rate-limit and token health bars, one office per project, orchestrator characters, drag-to-form teams, and tasks pulled from a visible board. See the [current feature set and roadmap](https://github.com/pixel-agents-hq/pixel-agents/blob/3537e140c2094761beae748592aeb92ece8edfdd/README.md#features).

This is a more relevant benchmark than building a new pixel renderer from scratch. Its provider/adapter boundary also supports the proposed principle: Codex, Claude, Hermes, and OpenRouter-backed workers should emit one normalized event model.

### Hermes Pixel UI — rooms as work semantics

- Repository: [`davinson-pezo/hermes-pixel-ui`](https://github.com/davinson-pezo/hermes-pixel-ui)
- Reviewed head: [`f85fd6d0952936582b07176f4536b63ab726e632`](https://github.com/davinson-pezo/hermes-pixel-ui/tree/f85fd6d0952936582b07176f4536b63ab726e632)

This separate project moves agents between rooms by activity: desks for active execution, an archive for research and files, a meeting room for planning, a brew bar for waiting, and recharge for completion. Its README states that the mapping is heuristic. See the [office map](https://github.com/davinson-pezo/hermes-pixel-ui/blob/f85fd6d0952936582b07176f4536b63ab726e632/README.md#office-map).

The room model is useful, but Nexus should map rooms to **workflow phases and verified states**, not inferred vibes. For example: Discovery Room, Research Lab, Architecture Table, Build Floor, Test Lab, Evidence Gate, Human Review, and Shipped Archive.

### Naming warning: two different “Hermes” surfaces

There is also a separate [`hermes-hq/hermes-ide`](https://github.com/hermes-hq/hermes-ide) product with its own Pixel Office plugin. That IDE project is not the Nous Research Hermes Agent plugin above, and its repository uses BSL 1.1 rather than MIT. The two should not be conflated during design or licence review.

---

## 4. Recommended product synthesis

The strongest product is not “Grok Bot with pixel art.” It is a **visual, evidence-backed product factory for non-technical founders**.

### User-facing journey

1. **Founder Room:** a spoken or typed group conversation turns a fuzzy idea into goal, user, problem, constraints, definition of done, and risk boundaries.
2. **Research Lab:** background researchers inspect competitors, source material, standards, and proven skill patterns while the conversation continues.
3. **Planning Table:** the orchestrator converts the agreed vision into a spec, dependency tree, agent roster, ownership, model tiers, budget, and gates.
4. **Build Floor:** named specialists work in parallel in isolated workspaces; the user sees the real task, model tier, cost, files, and status for each.
5. **Test Lab:** agents cannot visually “finish” until the relevant checks run against the exact deliverable.
6. **Evidence Gate:** claims are bound to the current commit or artifact, commands, results, screenshots, unresolved risks, and approvals.
7. **Human Polish Desk:** the system produces a clean, bounded packet for an external engineer when the remaining work genuinely requires specialist judgment.
8. **Launch Room:** only evidence-backed deliverables move to release-ready; “95% complete” is represented as explicit open gates, never a confidence guess.

### Minimum visual state model

Every agent card or character should expose:

- name and role;
- assigned outcome and owner;
- parent/orchestrator relationship;
- model/provider tier and why it was routed there;
- workspace/branch and permission boundary;
- current state: queued, researching, planning, building, testing, waiting, blocked, failed, verified, or shipped;
- elapsed time, token/cost budget, and actual spend;
- active tool and latest meaningful event;
- gates passed, gates remaining, and evidence link;
- handoff target and next decision required.

### Non-negotiable design rule

**Animation is not evidence.** A character sitting at a desk only means a lifecycle event says it is active. A character reaches “Verified” only when the authoritative gate ledger closes against the exact current artifact. This is the product boundary that differentiates Nexus from a playful monitor and from a generic multi-agent chat.
