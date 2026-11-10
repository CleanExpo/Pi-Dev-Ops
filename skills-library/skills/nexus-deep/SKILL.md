---
name: nexus-deep
description: Governed, evidence-led senior engineering orchestration for deep audit, research, design, implementation, challenge, simplification and verification. Routes through existing Senior Harness, skill-selector and Done gate; never self-authorises a task. Use when a task asks for /deep, NEXUS DEEP, or deep senior engineering work that needs governed discovery and verification.
---

# NEXUS DEEP — engineering discipline adapter (Phase 1)

This is a **discovery and workflow adapter**, not a second orchestrator and not production enforcement. Its presence in a skills catalog does not prove hooks, CI or model routing are installed.

## Invocation
User: `/deep <audit|research|design|build|challenge|simplify|verify|status> <target>`, or natural language: "Deep audit/build/verify ...". Until a launcher is installed, the text command is a **skill selection cue only**; read `commands/deep.md` for the proposed Claude adapter.

## Control flow
1. Preserve the literal user objective; identify target repo, observed Git HEAD, local date/time and trustworthy source coverage.
2. Run existing `done-harness` preflight/selftest before mutation. Missing, stale or invalid contract means **read-only** until properly locked. No invented green states.
3. Invoke existing `senior-harness-control`; use `skill-selector` for just the current phase. Do not read/inject the entire catalog or install unreviewed GitHub skills.
4. Freeze scope and measurable acceptance criteria before code. Choose a risk tier *advisory only*. Permission decisions must come from trusted runtime policy.
5. Apply the smallest relevant lenses from `references/TEAM-CONTRACT.md`; split builder and reviewer contexts. Do not let a reviewer mint its own independent attestation.
6. Produce bounded alternatives and red flags. For UI, require real browser/Playwright evidence. For dependencies, verify pinned sources and license/security. For code, measure regression, performance and bloat vs baseline.
7. Pass code through existing `proof-discipline`, `adversarial-review` and protected CI as warranted. A model-generated review never counts as a deterministic control.
8. Output observed facts, source+revision, test commands/results, missing controls, proposed next actions, and permission boundary. Use **BLOCKED**, **UNPROVEN**, **AWAITING_APPROVAL** or narrowly **VERIFIED** only when earned.

## Safety
Never merge, deploy, delete, spend, publish, send external messages, reveal credentials or weaken hooks without an existing authenticated approval. Never claim the offline `scripts/nexus_deep_cli.py` creates authority. A prompt, a user-supplied manifest and a local PASS string are not trusted signatures.

See `references/SPEC.md`, `references/BUILD.md`, `references/INVOKE.md` and `references/TEAM-CONTRACT.md`.
