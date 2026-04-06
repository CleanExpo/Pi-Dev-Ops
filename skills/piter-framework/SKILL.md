---
name: piter-framework
description: 5-pillar AFK agent setup - Prompt, Intent, Trigger, Environment, Review.
---

# PITER Framework

## P - Prompt
Spec prompts with verification commands, not chat messages.

## I - Intent
Classify: bug, feature, chore, spike, hotfix. Each routes differently.

## T - Trigger
CLI -> webhook -> cron -> CI. Progress from manual to automatic.

## E - Environment
Isolated workspace. Disposable. API keys via env vars.

## R - Review
Self-review (closed loop) -> CI review -> Human review (PR only).
