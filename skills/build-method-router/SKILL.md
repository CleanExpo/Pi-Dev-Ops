---
name: build-method-router
description: Use when a founder/non-coder gives a plain-English command, repo URL, or launch/build request and needs Pi-Dev-Ops to choose the correct build method automatically before any coding starts.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [routing, intake, build-method, non-coder, senior-engineer]
    related_skills: [senior-engineer-workflow, launch-project-audit, ship-it]
---

# Build Method Router

## Overview

This is the front door for non-coder commands. The operator should not need to know whether a request is a spike, repo intake, feature build, bug fix, launch audit, hotfix, refactor, or ship gate. This skill classifies the command, chooses the smallest safe build method, and then hands off to the existing Pi-Dev-Ops machinery.

The router exists to prevent the common failure mode: treating every impressive GitHub link or broad product sentence as "start coding". External repos and capability claims require intake first, not immediate implementation.

## When to Use

Use this skill first when the command contains:

- a GitHub/GitLab/Bitbucket URL;
- "look at this repo", "can we use this", "bring this in", "is this useful";
- "build", "fix", "ship", "launch", "audit", "integrate", "upgrade", "implement";
- unclear founder language where the build type is not obvious;
- a repo capability claim, such as "40+ providers", "built-in tools", "Rust core", "ships out of the box".

Do not ask the user to pick the method unless the next step is destructive, expensive, credential-changing, or external-facing.

## Command Classes and Build Methods

| Command signal | Intent | Build method | First skill / gate |
|---|---|---|---|
| Bare repo URL, "look at this", capability claim | `repo-intake` | Read-only external repo intake | `build-method-router` then `launch-project-audit` |
| "research", "compare", "evaluate", "is this better" | `spike` | Research spike | `senior-engineer-workflow` + spike template |
| "add", "implement", "integrate", "support" | `feature` | Senior engineer feature lane | `senior-engineer-workflow` |
| "bug", "broken", "not working", "error" | `bug` | Reproduce-diagnose-fix lane | `senior-engineer-workflow` |
| "urgent", "production down", "P0" | `hotfix` | Minimal hotfix lane | `senior-engineer-workflow` |
| "cleanup", "upgrade", "refactor", "migrate deps" | `chore` | Maintenance lane | `senior-engineer-workflow` |
| "ship it", "launch readiness", "is this ready" | `ship-it` / `launch` | Launch pre-flight, propose-only until approval | `ship-it` |

## Repo Intake Method

For a bare repo URL or repo capability claim, do this before deciding to build:

1. Clone shallow into a temp/sandbox directory.
2. Read `README.md`, package manifests, lockfiles, Dockerfiles, CI, `AGENTS.md`/`CLAUDE.md`, and docs index files.
3. Identify stack, build commands, test commands, runtime requirements, license/security posture, and integration fit.
4. Classify the repo:
   - `reference-only` — learn patterns, do not import code.
   - `tool-adoption` — install/run as an external tool.
   - `fork-and-adapt` — fork into a sandbox; preserve license notices.
   - `vendor-risk` — useful but too risky/bloated/incompatible.
   - `not-fit` — no immediate Pi-Dev-Ops use.
5. Produce a one-screen recommendation with:
   - what it is;
   - why it matters;
   - whether it enhances Pi-Dev-Ops;
   - build method selected;
   - next lane and verification commands.
6. Only after this can a feature/chore/spike lane start.

## Example: can1357/oh-my-pi

Input:

`https://github.com/can1357/oh-my-pi.git — most capable agent surface, 40+ providers, 32 tools, LSP/DAP ops, Rust core.`

Correct route:

- Intent: `repo-intake`, not `feature`.
- First action: read-only clone and architecture scan.
- Likely method: compare/adopt patterns for agent surface design, provider registry, tool runtime, LSP/DAP integration, and Rust-native performance boundaries.
- Do not immediately merge or copy code into Pi-Dev-Ops.
- If useful, create follow-on lanes:
  1. spike: compare oh-my-pi surface against Pi-Dev-Ops TAO/Hermes surface;
  2. feature: add one missing provider/tool registry capability;
  3. chore: document integration/non-integration decision;
  4. security/legal: license and dependency review before vendoring.

## Senior Engineer Gate Binding

Every selected build method except read-only repo intake must create or update Senior Engineer workflow evidence:

```bash
python .harness/workflows/senior_engineer_workflow.py init \
  --intent <feature|bug|chore|spike|hotfix> \
  --risk <low|medium|high> \
  --expected-path '<scoped/path/**>' \
  --required-command '<real verification command>'
```

Then complete:

```bash
python .harness/workflows/senior_engineer_workflow.py validate <manifest> <evidence>
```

## Routing Rules

1. Repo URL alone never means "build immediately". It means `repo-intake`.
2. Capability marketing claims are treated as hypotheses until verified from files/tests.
3. Broad founder requests become the smallest safe lane, not a mega-build.
4. Feature work cannot start until the connected path and verification path are named.
5. Launch/ship requests run `ship-it` pre-flight first; build only after the gate says what is build-ready.
6. External-facing release, push, secret, payment, destructive migration, or new service provisioning still requires the governance gate.

## Output Format

For each command, produce:

```text
Route: <intent>
Build method: <method>
Why: <one sentence>
First gate: <skill/gate>
Next action: <exact command or repo scan step>
Verification: <test/check/probe>
Stop condition: <complete | blocked | needs governance>
```

## Verification Checklist

- [ ] The command was classified before coding.
- [ ] A bare repo URL routed to `repo-intake`.
- [ ] The selected method is the smallest safe method.
- [ ] Existing project skills are reused; no duplicate build pipeline invented.
- [ ] Senior Engineer evidence is required for non-trivial code changes.
- [ ] Any external repo adoption includes license/security/dependency review.
