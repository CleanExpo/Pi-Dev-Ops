# AI Enhancement Workflow

## Goal

Remove the generated-render feel without using Remotion for the next stage.

## Order Of Operations

1. Generate source stills/keyframes.
2. Generate AI video clips from approved stills.
3. Assemble clips, verified product plates, captions, VO, music, and SFX in AI editor.
4. Export master.
5. Run enhancement/upscale only after picture is locked.
6. Run final QA.

## Enhancement Candidates

### Topaz Video AI

Use for:

- upscale
- denoise
- stabilization
- sharpening
- detail recovery

Guardrail:

- Do not over-sharpen faces, hands, carpet texture, or UI text. Plastic enhancement fails QA.

### Adobe / CapCut / Descript Native AI

Use for:

- speech cleanup
- captions
- background cleanup
- quick visual fixes
- social cutdowns

Guardrail:

- Native editor AI is allowed for polish, not product invention.

## QA Checks

- video and audio streams present
- audio duration not longer than video by more than 100ms
- captions readable
- no warped text/logos/UI
- no plastic AI enhancement look
- no hallucinated product claims
- no unclear generated-media or stock rights
