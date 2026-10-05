---
name: opus-adversary
description: Run a Claude-native adversarial review using an Opus subagent to challenge the design, find race conditions, and pressure-test assumptions on a change you just made. Use this as the default pre-merge gate on anything non-trivial — it costs nothing extra on Anthropic Max and gives genuine model-diversity (the reviewer is a different model from the writer). Replaces the role of `/codex:adversarial-review` for routine PRs; reserve Codex for high-stakes only.
---

# Opus-as-adversary (default pre-merge gate)

You wrote the code. Now you spawn an Opus subagent in adversarial mode to challenge it. A genuinely different model in the same family — the disagreement signal is real, and the cost is zero on Anthropic Max.

This is the everyday two-model gate. Use it routinely; reach for `adversarial-review` only when the change is genuinely dangerous.

## When to invoke

- Before opening a PR you intend to merge today
- After a non-trivial change (>50 lines, multi-file, or touching shared state)
- When you suspect you may have a blind spot (you've been deep in the change for a while)
- Before reporting "task complete" on anything non-trivial in autonomous mode

## When NOT to invoke

- Doc-only changes
- Pure formatting / linting
- Generated code with no logic surface
- The same change you just had Opus review — don't loop

## How to run it

Spawn an `Agent` call with `subagent_type: "general-purpose"` (or `Plan` for design-level pushback), `model: "opus"`, and an adversarial prompt.

The prompt template:

```
You are reviewing a change another model just made. Your job is to find what
it missed — not to validate. Be skeptical, not agreeable.

## What changed
<paste the diff or list of files + summary>

## Why it changed
<one sentence: what problem this solves>

## Your job
For each concern below, dig into the actual code and report:
1. Race conditions, ordering bugs, concurrency assumptions that may not hold
2. Error paths I didn't handle, or handled wrong
3. Edge cases at boundaries (empty, max, null, unicode, timezone, large input)
4. Hidden assumptions about caller behavior, env state, or data shape
5. Reversibility — can this be rolled back cleanly if wrong?
6. Tests that would have caught a real bug here but don't exist
7. Anywhere I picked the obvious approach when a different design would be safer

Format your response as a numbered list. For each item, cite file:line.
End with a verdict: APPROVE / APPROVE WITH NOTES / BLOCK + one sentence why.
Be terse. No preamble, no praise.
```

Always pass `model: "opus"` so the adversary is a different model from the writer. Without that override, you'd just be reviewing yourself.

## Handling the output

Treat the Opus verdict as advisory, not binding. For each concern:
- **APPROVE**: ship.
- **APPROVE WITH NOTES**: address what's clearly right, note rejections in the PR body.
- **BLOCK**: do not merge until resolved or the user overrides.

Do not silently agree with everything Opus says — sometimes the original Sonnet design was right and Opus is being overcautious. Push back when warranted; cite your reasoning.

## Pairing with adversarial-review

For changes that fail the high-stakes test in `adversarial-review` (auth, payments, migrations, etc.), run **both**: Opus first, then Codex. Two-model + cross-vendor confirmation. Different blind spots, layered defense.

For everything else, Opus alone is enough.

## Autonomous-loop integration

In the Pi-Dev-Ops autonomous loop:
- Run this skill before every `git push` to a branch that will open a PR
- If verdict is BLOCK, fix in place; do not push
- Log the Opus session/concerns to the PR body so reviewers see the gate ran
- Skip on docs/test-only/dep-bump-only diffs (use `git diff --stat` to filter)
