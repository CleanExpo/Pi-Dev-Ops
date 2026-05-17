---
job_id: ra-2026-05-15-wave-1-launch
created: 2026-05-17
type: ai-video-production-research-brief
status: research-ready
---

# RA Wave 1 AI Video Upgrade Brief

## Decision

Remotion is done. It produced a useful reference render: story order, timing, product proof, and voiceover are validated. It must not be used as the next production substrate.

The next stage is an AI video production workflow:

1. Generate premium source stills and keyframes.
2. Animate selected scenes with AI image-to-video/video-to-video tools.
3. Assemble, caption, and polish in an AI video editor.
4. Add AI-assisted audio, SFX, enhancement, and upscale.
5. Run market, licensing, and product-truth QA before publish.

## Production Principle

The product UI is truth. AI tools can enhance, frame, animate, texture, and package the story. They cannot invent product screens, customer data, claims, logos, standards, or workflows.

## Recommended Tool Bakeoff

### Tier 1: Test First

- **Adobe Firefly**: best first test where commercial-safety positioning, image/video generation, audio/color controls, and editor-style workflow matter.
- **Runway Gen-4**: best first test for controlled image-to-video, reference-driven motion, and performance/video workflows.
- **Luma Ray**: best first test for image-to-video and video-to-video modification where prompt adherence and video modification matter.

### Tier 2: Specialist Tools

- **Kling 3.0**: test for cinematic realism and strong image-to-video output, but require rights/commercial review before production.
- **CapCut**: use for fast social assembly, captions, background removal, music integration, and 9:16 cutdowns.
- **Descript**: use if transcript-first editing, dubbing/localization, or voice cleanup becomes central.
- **Topaz Video AI**: use for upscale, denoise, stabilization, sharpening, and final enhancement.

### Source Image Tools

- **Gemini/Nano Banana**: source still generation/editing and practical visual ideation.
- **Ideogram**: use for text-heavy stills and thumbnail variants where text accuracy matters.
- **Adobe Firefly**: use where commercially safer image generation is the priority.
- **Midjourney**: use only for high-aesthetic non-product concept stills; do not use for exact UI or claims.

## Scene Strategy

### Keep as factual reference only

- Scene 3: close job / editability invariant.
- Scene 4: chain-of-custody / storage proof.
- Scene 5: DR/NRPG inbound job proof.
- Scene 7: proof numbers.
- Scene 9-10: CTA and lockup.

These scenes can be re-framed and enhanced, but product content must come from captured/verified source screens, not generated hallucination.

### Rebuild with AI video generation

- Scene 1: premium hook frame and subtle motion.
- Scene 2: cinematic problem montage: wet carpet, camera roll, paperwork, late-night laptop, insurer/admin pressure.
- Scene 6: Australian-built / Brisbane identity moment.
- Transitions: premium motion texture between chaos, proof, and CTA.
- Thumbnail: generated/designed still, not a raw frame if a better market frame wins.

## Researcher Workstreams

### 1. AI Video Production Researcher

Outputs:

- `02-ai-generation-tool-shortlist.md`
- `03-scene-generation-plan.json`
- `prompt-and-reference-frame-pack.md`

Questions:

- Which tool creates the best scene 2 problem montage?
- Which tool creates the best scene 6 Brisbane/Australian-built identity moment?
- Which tool preserves brand mood without generic AI slop?
- Which tool has commercial-use clarity?

### 2. AI Image Researcher

Outputs:

- source still prompts
- thumbnail variants
- keyframe pack for image-to-video
- negative prompts and product-truth constraints

Rules:

- No fake product UI.
- No fake real customers.
- No recognisable people unless licensed/consented.
- No generated standards/legal citations.
- Text-heavy visuals go through Ideogram or editor overlay, not generic image models.

### 3. AI Video Editor Researcher

Outputs:

- `ai-editor-workflow.md`
- caption workflow
- 1:1 master assembly path
- 9:16 cutdown path

Candidates:

- Firefly editor for generative assembly and Adobe ecosystem.
- CapCut for fast social packaging.
- Descript for transcript/voice-led edit if needed.
- Runway/Luma workspaces for generation management.

### 4. AI Sound And Enhancement Researcher

Outputs:

- `04-sound-design-brief.json`
- music/SFX candidate list
- enhancement workflow
- loudness and final stream validation

Candidates:

- ElevenLabs SFX for generated sound design under current terms.
- Adobe audio tools for Enhance Speech / cleanup.
- CapCut/Firefly editor audio layers for fast assembly.
- Topaz Video AI for final enhancement/upscale if the generated clips need it.

### 5. Market And QA Researcher

Outputs:

- `01-market-readiness-rubric.json`
- `07-licensing-proof-sheet.md`
- `08-final-video-qa-report.json`

Blocking checks:

- no leaked customer data
- no unclear asset rights
- no hallucinated UI or claims
- no warped logo/text
- no voiceover clipping
- captions readable on mobile
- first frame works silent

## Required New Skills

### `ai-video-production-researcher`

Purpose: Select and evaluate AI video generation/editing tools per scene.

Triggers: "AI video editor", "image to video", "next level video", "prize winning video", "enhanced video production".

Outputs:

- `ai-generation-tool-shortlist.md`
- `scene-generation-plan.json`
- `prompt-and-reference-frame-pack.md`

### `ai-image-director`

Purpose: Generate source stills/keyframes that are cinematic, brand-safe, and usable for image-to-video.

Triggers: "source frames", "keyframes", "thumbnail", "image generation", "hero frame".

Outputs:

- source prompts
- negative prompts
- keyframe contact sheet
- text/logo safety notes

### `ai-video-editor`

Purpose: Assemble AI-generated clips, source screens, captions, music, SFX, and exports into the market asset.

Triggers: "AI edit", "CapCut", "Firefly editor", "Descript", "captions", "social cut".

Outputs:

- `ai-editor-workflow.md`
- `edit-decision-list.json`
- `platform-export-checklist.md`

### `ai-video-rights-qa`

Purpose: Validate commercial rights, generated-media risks, likeness/data safety, and platform publish readiness.

Triggers: "publish", "commercial rights", "licensing", "final QA", "market-ready".

Outputs:

- `licensing-proof-sheet.md`
- `final-video-qa-report.json`

## Immediate Bakeoff

Create two clips in each Tier 1 tool:

1. Scene 2 problem montage: wet carpet, phone photo chaos, admin paperwork, late-night laptop.
2. Scene 6 Australian-built identity: premium Brisbane/restoration-business identity without tourist stock.

Score each output against:

- realism
- brand fit
- motion control
- absence of AI artefacts
- commercial/rights clarity
- editability
- speed/cost

Winner becomes the primary next-stage production tool. Runner-up becomes fallback.

## Current Recommendation

Start with Adobe Firefly, Runway Gen-4, and Luma Ray. Keep CapCut ready for social assembly and Topaz ready for enhancement. Do not use Remotion for the next production stage.

## Sources

- Runway Gen-4 Video: https://help.runwayml.com/hc/en-us/articles/37327109429011-Creating-with-Gen-4-Video
- Luma Ray: https://lumalabs.ai/ray
- Luma Ray3 Modify FAQ: https://lumalabs.ai/learning-hub/ray3-modify-faqs
- Adobe Firefly Image to Video: https://www.adobe.com/products/firefly/features/image-to-video.html
- Adobe Firefly AI innovations: https://news.adobe.com/news/2026/04/adobe-new-creative-agent
- CapCut AI Video: https://www.capcut.com/tools/ai-video
- Topaz Video AI upscaling docs: https://docs.topazlabs.com/video-ai/how-to-guide/upscale-1080-to-4k
- Google Gemini image generation docs: https://ai.google.dev/gemini-api/docs/image-generation
- Ideogram text rendering: https://ideogram.ai/features/text-rendering/
- ElevenLabs Sound Effects terms: https://elevenlabs.io/sound-effects-terms
- Artlist commercial projects and advertising: https://help.artlist.io/hc/en-us/articles/6185461392029-Commercial-projects-and-advertising
