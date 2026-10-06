---
name: remotion-professionalism
description: Use when a Remotion video needs a professional marketing QA pass for brand fit, readability, pacing, typography, polish, and not-looking-generated.
owner_role: Quality Director
status: remotion-wave-1
intents: remotion-professionalism, video-qa, professional-video
---

# remotion-professionalism

QA rubric for `/remotion-video`.

## Rubric

Score each 1-5:

- Hook clarity.
- Audience fit.
- Visual hierarchy.
- Typography and legibility.
- Motion restraint.
- Voice pacing.
- CTA clarity.
- Brand consistency.
- Evidence/proof quality.
- Overall polish.

Any score below 3 blocks production render until revised.

## Verification checklist

- [ ] Looks intentional, not like a generated slide deck.
- [ ] Viewer understands the offer in 5 seconds.
- [ ] CTA is singular.
- [ ] Brand system is respected.

## Ship gate (Prove mode)

When this skill changes something that already exists in a way a person would judge (wording, behaviour,
design, a model or prompt, a cost line), the change ships only after it beats the current version. Call the
Skill tool with "gauntlet-loop" and follow its Prove mode. Mechanical fixes that a hard check proves (a
broken link repaired, a failing test made to pass) do not need it.
