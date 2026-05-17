# OpenAI Max Keyframe Runbook

Job: `ra-2026-05-15-wave-1-launch`

This is the next-stage production pass. The Remotion MP4 is reference only. Use OpenAI Max to create premium stills/keyframes, then use Artlist for licensed motion/audio assets.

Reference material:

- Contact sheet: `reference-contact-sheet.jpg`
- Extracted reference frames: `reference-frames/frame-01.jpg` through `reference-frames/frame-10.jpg`
- Reference render: `../../output/ra-wave-1-launch-poc.mp4`

## Non-Negotiables

- Do not generate fake RestoreAssist product UI.
- Do not generate real customer names, addresses, claim numbers, insurer names, or competitor logos.
- Do not use recognisable faces.
- Do not generate legal/standards text. Put exact proof text in editor overlays only.
- Product screens come from verified screenshots or Remotion reference frames.
- Style target: premium restoration trade SaaS, Australian, forensic, calm, high-trust.

## Global Style Prompt

Use this style block in every OpenAI image generation:

```text
Premium cinematic commercial frame for an Australian restoration business SaaS launch video. Realistic, restrained, high-trust, tactile trade-business environment, quiet forensic confidence. Square 1:1 composition, designed for LinkedIn feed. Colour palette: deep navy, clean white, measured amber highlights, muted restoration-site neutrals. Lighting is natural and motivated, not glossy stock. Shot as a premium documentary commercial, shallow but not blurry depth of field, clean negative space for later typography. No fake app UI, no readable private data, no logos, no recognisable faces, no generic smiling office stock, no disaster-movie drama.
```

## Keyframe 01: Silent Hook

Use reference frames: `frame-01.jpg`, `frame-02.jpg`

Prompt:

```text
Create a premium 1:1 still frame for the opening of a restoration-business SaaS launch video. A late-night work surface after a water-damage job: damp field notes, phone with blurred photo grid, laptop glow, work gloves, a small pool of warm desk light, deep navy shadows. The feeling is "finished the dry-out at three, paperwork kept you till nine." Leave clean negative space in the upper third for editor-added text. No readable private data. No fake software UI. No faces. No brand logos. No melodrama.
```

Acceptance:

- Works silently as a first frame.
- Clearly communicates restoration admin pain within 1 second.
- Has room for editor overlay text.

## Keyframe 02: Problem Montage Plate

Use reference frames: `frame-02.jpg`, `frame-03.jpg`

Prompt:

```text
Create a cinematic restoration admin chaos keyframe. Wet carpet edge, drying equipment partly visible, a phone showing an indistinct camera roll of site photos, paperwork, and a laptop in the background. The subject is not a flood disaster; it is the administrative mess after field work. Premium documentary commercial look, realistic Australian home/restoration context, no people visible except maybe anonymous hands out of focus. No readable addresses, no insurer names, no fake app screens, no logos. Keep composition clean enough to animate with a slow push-in.
```

Acceptance:

- Specific to restoration, not generic office paperwork.
- Feels expensive and credible.
- Can be animated as a 3-5 second slow move.

## Keyframe 03: Product Truth Transition

Use reference frames: `frame-03.jpg`, `frame-04.jpg`, `frame-05.jpg`

Prompt:

```text
Create a premium transition keyframe that frames a verified product screenshot as factual evidence. The app screen area must remain a clean blank placeholder where the real screenshot will be composited later. Surround it with subtle forensic cues: soft grid, metadata texture, restrained light sweep, deep navy background, small amber glints. Do not invent UI. Do not include text. The screen placeholder must be perfectly rectangular and readable for later compositing.
```

Acceptance:

- Does not hallucinate product UI.
- Gives the editor a clean plate for real screenshot insertion.
- Feels forensic, not cyberpunk.

## Keyframe 04: BYO Storage Proof

Use reference frames: `frame-04.jpg`, `frame-05.jpg`

Prompt:

```text
Create a premium forensic proof still for a SaaS feature about customer-controlled storage and chain-of-custody. Abstract but grounded: a verified photo card, subtle metadata rails, secure storage motif, deep navy surface, warm highlight, crisp material detail. Leave exact text labels blank for editor overlay. Do not generate SHA strings, GPS coordinates, standards references, or cloud-provider UI. No fake dashboards. No logos.
```

Acceptance:

- Feels like evidence custody, not generic cybersecurity.
- Leaves all exact proof text to the editor.

## Keyframe 05: Australian-Built Identity

Use reference frames: `frame-06.jpg`, `frame-07.jpg`, `frame-08.jpg`

Prompt:

```text
Create a premium Australian-built identity keyframe for a Brisbane restoration SaaS. Subtle early morning light, practical trade-business setting, restoration equipment, a work ute or workshop detail, and a clean modern technology layer implied through light and composition. Avoid tourist skyline cliches. Avoid kangaroo/beach/Australian flag tropes. No recognisable faces, no logos, no fake app screens. It should feel Brisbane-built, serious, useful, and credible.
```

Acceptance:

- Australian without cliche.
- Restoration-business specific.
- Premium enough for a market launch.

## Keyframe 06: Final CTA Thumbnail

Use reference frames: `frame-08.jpg`, `frame-09.jpg`, `frame-10.jpg`

Prompt:

```text
Create a premium final thumbnail/background frame for a RestoreAssist launch CTA. Deep navy field, subtle restoration-site texture, refined amber highlight, clean central space for real logo and text to be added later. The image should feel trustworthy and practical, not decorative. No generated words, no fake logo, no UI, no people, no stock-photo look.
```

Acceptance:

- Holds as a thumbnail before text is added.
- Does not compete with logo or CTA.

## Run Order

1. Generate Keyframe 02 first. It is the highest-value upgrade over the Remotion reference.
2. Generate Keyframe 05 second. It solves the Australian-built identity problem.
3. Generate Keyframe 01 third. It creates the market hook.
4. Generate Keyframes 03, 04, and 06 as clean production plates for compositing.

## First-Pass Scoring

Score each generated still from 1-5:

- restoration specificity
- premium commercial quality
- no AI artefacts
- no hallucinated UI or private data
- editability for motion/captions
- brand fit

Reject any still immediately if it includes fake UI, readable private data, warped text, recognisable faces, or generic office stock energy.
