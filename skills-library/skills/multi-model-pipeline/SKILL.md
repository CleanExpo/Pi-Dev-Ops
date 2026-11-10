---
name: multi-model-pipeline
description: "Handoff templates for the four-stage build line: Grok Strategy spec, Claude Code Architecture blueprint on the Mac Mini, Codex coding, Claude Code Release gate. Use when work passes between Grok, Claude Code and Codex, or when a change starts from a Grok or research finding. Points to pr-release-gate, linear-sync, playwright-cli and session-handoff rather than restating them."
owner_role: Tier-Architect (cross-agent handoffs; templates only, gates live elsewhere)
status: active
automation: manual
---

# Multi-Model Pipeline

One change moves through four stages in order. Each stage hands the next a filled-in
template from this file. A stage that cannot fill every field stops and says which field is
missing; it never guesses. This skill only defines the handoffs. The gates themselves live in:

- [`pr-release-gate`](../pr-release-gate/SKILL.md): receipt on the head SHA, independent review, push and PR rules.
- [`linear-sync`](../linear-sync/SKILL.md): claim, progress and Done on Linear.
- [`playwright-cli`](../playwright-cli/SKILL.md): screenshots and video for UI changes.
- [`session-handoff`](../session-handoff/SKILL.md): stopping or passing work mid-stage.

| Stage | Agent | Input | Output |
|---|---|---|---|
| 1 Strategy | Grok (Guardian / research bots) | telemetry, research, founder ask | Strategy spec |
| 2 Architecture | Claude Code on the Mac Mini | spec + live code + skills library | Blueprint |
| 3 Coding | Codex | blueprint | commits on the branch |
| 4 Release gate | Claude Code | branch + blueprint + spec | receipt, review, draft PR, Linear update |

## House rules (every stage)

1. **Never press GitHub's "Update branch".** It makes a new head and voids the receipt and review.
2. **Run on the repo-pinned Node** (`.nvmrc` / `.node-version` / `engines`). Never switch it to make a run pass; a mismatch is a stop.
3. **Shape or layout fixes: check every combination** (each breakpoint, theme, state and data shape the blueprint lists), not just the one that was reported.
4. **A draft PR is not a safe place to leave half-done work.** Automation can ready and merge drafts. Finish the stage or hand off with `session-handoff`; never park unfinished work in a PR.
5. **Expired login = stop and alert.** If Claude, Codex, gh, Linear or any other login fails, stop the stage, alert Phill with what failed, and wait. Re-login is founder-only. Never work around it with an API key or another account.
6. No secrets in any handoff, spec, blueprint, log or PR body. Refer to a secret by its name only.

## Stage 1: Strategy spec (Grok → Claude Code)

```markdown
# Strategy spec: <short title>
- Spec ID: <date>-<slug>        Linear: <issue id or "to create">
- Repo(s): <owner/repo>
- Problem: <one or two sentences, what is wrong or missing, for whom>
- Evidence:
  - <fact> (source: <URL, dashboard, log name or file:line>, read <date time AEST>)
  - <fact> (source: ...)
- Success metric: <measurable target, e.g. "p95 checkout API < 200 ms over 24 h">
- How to measure it: <query, test or page that shows the metric>
- Constraints: <budget, deadlines, what must not change, data/privacy limits>
- Out of scope: <list>
- Confidence: <high | medium | low> and why
```

Every evidence line needs a source. No source, no line.

## Stage 2: Architecture blueprint (Claude Code → Codex)

Claude Code reads the live code on the Mini and the relevant skills before writing this.
Claim the Linear issue first (`linear-sync`).

```markdown
# Blueprint: <spec title>
- Spec ID: <from stage 1>       Linear: <id, claimed>
- Repo / base: <owner/repo> @ <origin/main SHA>
- Branch: <type>/<slug>   (CI-run prefix; never claude/)
- Pinned Node: <version from repo>   Package manager: <from repo>
- Files to change:
  - <path>: <what changes and why>
- Files to add: <path: purpose>
- Data / tables: <tables, columns, indexes, migrations; "none" if none>
- Tests to add or change: <test file: case it proves>
- UI evidence needed: <yes/no; if yes, each screen x breakpoint x theme x state to capture>
- Combinations to check (shape/layout): <full list>
- Safety limits:
  - Must not touch: <paths, tables, configs, secrets>
  - Max blast radius: <e.g. "only the checkout API route">
  - Rollback: <how to undo>
- Done when: <commands that must exit 0 + success metric from the spec>
```

## Stage 3: Coding (Codex → Claude Code)

Codex writes only what the blueprint lists. Anything outside it goes back to stage 2 as a
question, not into the code.

```markdown
# Coding report: <spec title>
- Blueprint: <spec ID>     Branch: <branch>     Head: <SHA>
- Files changed: <git diff --name-only>
- Outside blueprint: <none, or each file and why it was needed>
- Commands run on pinned Node <version>: <command: exit code>
- Open questions: <none or list>
```

## Stage 4: Release gate (Claude Code)

Follow [`pr-release-gate`](../pr-release-gate/SKILL.md) end to end; do not shortcut it here.
In short: provision on the pinned Node, run the full definition of done and the CI mirror,
get an independent review in the lane order that skill sets (Codex, then Cursor, then a fresh
Claude session), drain P0/P1, issue the receipt on the
exact head SHA, push, wait for GitHub to run that SHA, then open a **draft** PR with the
`env -u GIT_CONFIG_COUNT -u GIT_CONFIG_KEY_0 -u GIT_CONFIG_VALUE_0` prefix. For UI changes
attach Playwright screenshots and video for every combination in the blueprint. Comment the
PR link on Linear and move it to Done only when `linear-sync`'s Done rule is met (merged,
deployed to production and verified live), not on merge alone. Do not merge unless the merge lane
in `pr-release-gate` allows it.

```markdown
# Release report: <spec title>
- Linear: <id> (status)        PR: <link> (draft/ready as GitHub shows it)
- Head SHA (pushed): <SHA>     GitHub result for that SHA: <green / pending / red>
- Receipt: <PR_RELEASE_GATE_PASS on SHA ...>
- Independent review: <lane, reviewer, verdict, report path, files reviewed vs changed>
- UI evidence: <screenshot/video paths per combination, or "not UI">
- Success metric check: <how it will be measured after merge>
- Blocked / needs Phill: <none or list>
```

Jev may add an advisory review when Phill asks for one. It is extra input only: it cannot
supply the pr-release-gate independent PASS or the receipt.

Report results to Phill in four separate groups: prepared, verified (local checks), live
(GitHub green or deployed) and paid-value. Never call local checks "green".
