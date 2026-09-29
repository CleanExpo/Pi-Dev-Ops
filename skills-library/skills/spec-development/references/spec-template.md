# Spec: <feature name>

> Dir: `docs/specs/<YYYY-MM-DD>-<slug>/` · Author: <who> · Status: draft | clarified | judged | building | shipped
> Judge: <score>/100 <APPROVE | APPROVE-EXPERIMENT | REDUCE-SCOPE | REJECT> (<date>)

## Problem / intent
One paragraph: who hurts, what outcome we want, why now. No solution language.

## User stories
One per affected persona. Format:
- **As a** <persona>, **I want** <capability>, **so that** <outcome>.

## Functional requirements
Numbered, testable, tech-free. Each carries an evidence tag where it asserts a fact
about the existing system: `[VERIFIED file:line]` / `[INFERENCE]` / `[UNCONFIRMED]`.

| # | Requirement | Evidence |
|---|---|---|
| R1 | … | [VERIFIED lib/x.ts:42] |

## Acceptance criteria (Given / When / Then)
Each criterion must be executable by a test, a script, or a documented manual step.

1. Given …, When …, Then …

## Non-goals
Explicit exclusions — the scope fence. Anything here appearing in plan.md is a defect.

## Dependencies & constraints
Standing law that binds this feature (constitution rules, env vars, other epics/PRs).

## Clarifications
| Date | Question | Resolution |
|---|---|---|

## Risks
Top 3-5, each with the mitigation or the accepted exposure.
