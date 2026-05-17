# RA Wave 1 Prize Upgrade Shutdown Handoff

Timestamp: `2026-05-17T20:07:11+1000`

## Current State

The original Remotion render is now reference only:

- `remotion-studio/output/ra-wave-1-launch-poc.mp4`

The next-stage production packet is active here:

- `remotion-studio/briefs/ra-wave-1-prize-upgrade/09-openai-max-keyframe-runbook.md`
- `remotion-studio/briefs/ra-wave-1-prize-upgrade/10-artlist-production-picklist.md`
- `remotion-studio/briefs/ra-wave-1-prize-upgrade/11-next-stage-edit-decision-list.json`
- `remotion-studio/briefs/ra-wave-1-prize-upgrade/12-generated-keyframe-log.md`

Approved first market-upgrade image:

- `remotion-studio/briefs/ra-wave-1-prize-upgrade/generated-keyframes/scene-02-problem-montage-openai-max.png`

Status:

- Scene 2 problem montage keyframe is visually approved by Phill.
- OpenAI Max is the first source-still/keyframe substrate.
- Artlist.io credits are the first licensed footage/music/SFX substrate.
- No new paid video/editor/image subscriptions are approved by default.
- Product UI remains source-of-truth only; no generated product screens.

## Linear Status

Linear issue creation was attempted through the Pi-CEO MCP on 2026-05-17 and is blocked because `LINEAR_API_KEY` is not set in the MCP environment.

The continuation tasks are written in `14-linear-continuation-issues.json` with enough detail to replay into Linear once the key is present.

## Resume Command

Start from:

```text
Continue RA Wave 1 prize upgrade from remotion-studio/briefs/ra-wave-1-prize-upgrade/13-shutdown-handoff.md. Linear creation was blocked by missing LINEAR_API_KEY; replay 14-linear-continuation-issues.json into Linear, then continue generating approved keyframes with OpenAI Max and sourcing Artlist assets with license proof.
```

## Next Production Move

Generate the remaining OpenAI Max keyframes in this order:

1. Scene 6 Australian-built identity.
2. Scene 1 silent hook.
3. Scene 3 product-truth transition plate.
4. Scene 4 BYO storage proof plate.
5. Scene 8-10 CTA thumbnail/background.

After each approved image:

- copy it into `generated-keyframes/`
- append provenance to `12-generated-keyframe-log.md`
- commit and push

## Artlist Move

Source only the first seven assets from `10-artlist-production-picklist.md`:

1. one music bed
2. one transition whoosh family
3. one tactile UI click
4. two restoration/admin texture clips
5. one Australian trade-business texture clip
6. one forensic/data-custody texture clip

Before any asset enters the final timeline, update `07-licensing-proof-sheet.md`.
