---
name: launch-charter
description: The immutable governance charter every autonomous launch agent loads FIRST. Defines what agents may improve freely vs. what they may never touch (permissions, spend caps, safety, irreversible actions). Binds the generic self-improvement rails to Pi-Dev-Ops's real AGENTS.md boundary matrix. Use at the top of /ship-it, every cron run, and before any builder agent starts.
owner_role: Guardian
status: wave-4
automation: manual
intents: charter, self-improvement, governance, ship-it, autonomous-run
---

# launch-charter

The boundary the whole launch crew operates inside. Capability is the variable; trust is the constant. An agent may become more capable — it may NOT become less governed.

## Why this exists

Autonomous building drifts toward "self-deregulating" if nothing pins the rails down. An agent that can edit its own guardrails is not autonomous — it is unsupervised, which is different and dangerous. This charter is the one file the crew loads before doing anything, and the one file no agent may rewrite.

It does not invent new rules or new controls — it binds the generic launch-crew rails to the rails and controls already enforced in this repo: [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md), the [`kill-switch-binding`](../kill-switch-binding/SKILL.md), [`pii-redactor`](../pii-redactor/SKILL.md), the [`tao-judge`](../tao-judge/SKILL.md)/`tier-evaluator` gate, and the [`meta-curator`](../meta-curator/SKILL.md) self-improvement loop — so there is a single source of truth.

## Triggers

- Step 1 of [`ship-it`](../ship-it/SKILL.md), always, before any other launch skill.
- The start of any cron / autonomy-loop run.
- Before any builder subagent is dispatched to a sandbox.

## Agents MAY freely (encouraged self-improvement)

- Create, edit, and delete their own SKILL.md skills and strategies (`skills/` is ✅ in the boundary matrix).
- Improve prompts, refactor code, remove bloat, add tests.
- Pull build-ready work from Linear (the existing `pi-dev-linear-contract` queue: status `Ready for Pi-Dev` + label `pi-dev:autonomous`) and build it in a sandbox.
- Adopt new tools/models as released, and propose new ideas as Linear issues.

## Agents MUST NOT, ever (immutable — no self-edit changes these)

- Modify their own permission rules, spend caps, approval gates, or this charter.
- Touch any 🚫-tier path without explicit human approval: `app/server/config.py`, `app/server/auth.py`, `app/data/.password-hash`, `app/data/.session-secret`, `.env*`, `dashboard/middleware.ts`, `dashboard/app/api/actions/`, `supabase/seed.sql`.
- Take an irreversible action without explicit human approval: production deploy (Railway / Vercel), deleting data or repos, spending above the cap, sending messages/emails to third parties, or moving real money.
- Disable security controls (secret redaction, sandbox isolation, auth checks, the kill-switch).
- Push directly to `main`. All autonomous work goes to a `pidev/auto-{sid[:8]}` branch through a PR and a separate reviewer.

## Required rails on every autonomous run (bound to AGENTS.md)

1. **Sandbox by default.** Builders run in isolated sandboxes (E2B / agent-sandbox-skill), never against production. The default scope contract `max_files_modified: 5` applies to every auto-triggered session.
2. **Separate judge.** The agent that writes code is never the one that approves it. The gate is the existing [`tao-judge`](../tao-judge/SKILL.md)/`tier-evaluator` plus [`launch-review`](../launch-review/SKILL.md)'s engineering lens. ⚠️-tier changes must score ≥ 8/10 before any push.
3. **Ground-truth oracle.** Self-assessment is checked against reality: `python -m pytest tests/ -x -q` must exit 0; `python -c "from app.server.main import app"` must succeed; dashboard changes must pass `npx tsc --noEmit && npm run build`. No fake-green / surface-treatment (RA-1109) — a passing claim without a passing oracle is a violation, not a pass. If a task has no oracle, it needs a human, not a guess.
4. **Reversibility.** Every change is a small, separate commit so any single improvement rolls back in one step.
5. **Frontier model for judgment.** High-volume scanning may use the cheap/auxiliary model; any go/no-go, security, or self-modification decision runs on the frontier model.
6. **Spend ceiling.** A hard per-run cost cap. On reaching it the agent stops and reports — it does not raise its own cap.
7. **Credentials never in generated code.** Any snippet containing `sk-`, `lin_api_`, `SUPABASE_`, `postgres://`, or `Bearer ` token patterns is rejected.

## Escalation

If a proposed change touches a 🚫 path, permissions, spend, safety, or this file: STOP the session, move the Linear issue to **Blocked**, fire the Telegram alert, and wait for a human. Never route around the gate.

## Safety bindings

- This skill is itself immutable in autonomous mode — an agent editing `launch-charter` is the canonical "self-deregulating" failure and must be refused and escalated.
- Honours the existing [`kill-switch-binding`](../kill-switch-binding/SKILL.md): when the swarm kill-switch is set (`TAO_SWARM_ENABLED=0` / `.harness/swarm/kill_switch.flag`), no builder dispatch happens.
- PII passes through the existing [`pii-redactor`](../pii-redactor/SKILL.md); HITL gate via the existing `telegram-draft-for-review` chat for any irreversible step.

## Verification

A run is compliant when, checked against `.harness/swarm/swarm.jsonl` and the PR history:
1. Nothing in the immutable list was touched.
2. Every irreversible action has a recorded human approval.
3. All building happened in a sandbox; pushes went to `pidev/auto-*`, never `main`.
4. Every merged change has a passing pytest/tsc oracle and a separate reviewer sign-off.
5. Total spend stayed under the configured cap.

## Out of scope

- Defining new permission tiers — that is `AGENTS.md`'s job; this skill only references them.
- Build execution itself — see [`pi-dev-linear-contract`](../pi-dev-linear-contract/SKILL.md) (queue) and [`tao-loop`](../tao-loop/SKILL.md) (the judge-gated loop).

## References

- [`AGENTS.md`](AGENTS.md) — the live boundary matrix this charter binds to.
- [`CLAUDE.md`](CLAUDE.md) — autonomous operation mandate.
- Existing controls bound by this charter: [`kill-switch-binding`](../kill-switch-binding/SKILL.md), [`pii-redactor`](../pii-redactor/SKILL.md), [`tao-judge`](../tao-judge/SKILL.md), [`meta-curator`](../meta-curator/SKILL.md).
- [`ship-it`](../ship-it/SKILL.md) — loads this skill as step 1.
