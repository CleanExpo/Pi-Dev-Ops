---
name: ship-it
description: A launch-readiness PRE-FLIGHT that runs before the existing ship-chain — load the charter, audit build-state, run the aggregated launch-review, propose enhancements, sync findings to Linear via the existing pi-dev-linear-contract, then STOP for a human go. On go it hands the approved, build-ready issues to the existing ship-chain / tao-loop, never re-implementing build/test/ship. Use on "ship it" / "run the launch crew".
owner_role: CoS
status: wave-4
automation: manual
intents: ship-it, launch-crew, launch-readiness
---

# ship-it

The Chief-of-Staff **pre-flight** that gets a product launch-ready, then hands off to the machinery that already exists. It deliberately does **not** duplicate `ship-chain` (the `/spec→/plan→/build→/test→/review→/ship` phase chain), `ship-release` (terminal ≥8/10 gate), or `tao-loop` (judge-gated build loop). It adds the missing front-end: governance + build-state audit + multi-lens review + backlog sync.

## Why this exists

`ship-chain` ships *one feature* through phases; it has no audit phase and no multi-lens review. `ship-it` answers the larger question — "is the whole product ready to launch, and what's the prioritized backlog to get there?" — then feeds that backlog into `ship-chain`/`tao-loop` rather than shipping anything itself.

## Triggers

- "ship it", "run the launch crew", "full launch-readiness pass".
- A scheduled nightly cron (runs steps 1–6 only; never auto-advances to build).

## Method

Run in order. Never skip step 1.

1. **Load [`launch-charter`](../launch-charter/SKILL.md) FIRST.** Governs everything below; never violate the immutable rails.
2. **[`launch-project-audit`](../launch-project-audit/SKILL.md)** — cheap-model bulk scan (rendergit), frontier for ambiguous calls → build-state + pipeline-stage map at `.harness/audits/audit-<date>.md`.
3. **[`launch-review`](../launch-review/SKILL.md)** — aggregate the existing audit lenses + the two new lenses → `.harness/audits/review-<date>.md`.
4. **[`launch-enhance-debloat`](../launch-enhance-debloat/SKILL.md)** — list strengthen/de-bloat/security changes (PROPOSE ONLY) → `.harness/audits/enhance-<date>.md`.
5. **Sync to Linear via [`pi-dev-linear-contract`](../pi-dev-linear-contract/SKILL.md)** — de-duplicated issues in the right project, priority-mapped, marking only safe/reversible work build-ready using the **existing** contract markers (status `Ready for Pi-Dev` + label `pi-dev:autonomous`). Do NOT invent new tags.
6. **STOP.** Show the human a one-screen summary: top criticals, what synced, what awaits approval. Do not build until the human says go (or has pre-approved the autonomy queue).
7. **On go: hand off, don't re-implement.** Build-ready issues flow into the existing autonomy path — `ship-chain` per feature, `tao-loop`/`tao-judge` for the judge-gated loop, `ship-release` as the terminal ≥8/10 gate. `ship-it` only kicks the parent dispatch and monitors; it never opens its own build/test/ship phases.

Keep total spend under the cap. Anything irreversible waits for an explicit human yes.

## Output

A one-screen human summary at step 6, the three audit artifacts under `.harness/audits/`, and the Linear issues from step 5. A `cos` orchestration row via `audit_emit.row(...)`.

## Safety bindings

- Step 1 is non-negotiable; the charter loads before any scan/review.
- Steps 2–5 are read-only / propose-only; nothing builds before the human gate at step 6.
- Cron runs steps 1–6 only.
- Build/test/ship are delegated to existing gated skills — `ship-it` adds no new push path and obeys the `pidev/auto-*` + ≥8/10 + spend-cap rails.

## Verification

1. The run logs steps 1→6 in `.harness/swarm/swarm.jsonl`, `launch-charter` first.
2. Each referenced skill is called by its exact `name` and produces its named artifact.
3. Step 7 invokes existing `ship-chain`/`tao-loop`/`ship-release` — no new build/test/ship logic appears in this skill.
4. Linear markers match the existing contract (`Ready for Pi-Dev` + `pi-dev:autonomous`); no invented tag.

## Out of scope

- Building, testing, or shipping features — delegated to `ship-chain`/`tao-loop`/`ship-release`.
- The Linear contract itself — owned by [`pi-dev-linear-contract`](../pi-dev-linear-contract/SKILL.md).
- Launch-calendar/GTM orchestration — see [`marketing-launch-runbook`](../marketing-launch-runbook/SKILL.md).

## References

- [`launch-charter`](../launch-charter/SKILL.md), [`launch-project-audit`](../launch-project-audit/SKILL.md), [`launch-review`](../launch-review/SKILL.md), [`launch-enhance-debloat`](../launch-enhance-debloat/SKILL.md).
- Existing machinery: `ship-chain`, `ship-release`, `tao-loop`, `tao-judge`, `pi-dev-linear-contract`.
- Wiring: add `"ship-it"` to `_INTENT_SKILLS` in `src/tao/skills.py` (see `SETUP.md`).
