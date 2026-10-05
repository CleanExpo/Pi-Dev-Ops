# Getting the quality you recorded for — HeyGen v3 engines, verified against the live account

Read this before rendering any avatar built from a to-camera recording. It exists
because a long capture buys a **higher-fidelity render path**, and the wrong API
call throws that away silently — the render still succeeds, it just looks like
the cheap path.

Everything in the "verified" sections below was checked against the live HeyGen
account on 2026-07-24, not taken from documentation. Where the public docs and
the account disagree, the account wins and the disagreement is called out.

## The thing that actually matters

The current API has three rendering engines, selected per request:

| Engine | `engine.type` | Default? | What it gives you |
|---|---|---|---|
| **Avatar V** | `avatar_v` | no — explicit opt-in | Highest fidelity. Cross-reference-driven animation, the most natural motion and lip-sync. |
| Avatar IV | `avatar_iv` | **yes** | Standard, broad coverage. Supports `expressiveness`. |
| Avatar III | `avatar_iii` | no | Dedicated photo-to-video pipeline; 4K for video-avatar looks. |

**Omitting `engine` silently renders Avatar IV.** No error, no warning, lower
fidelity. That single omission is the most common way a recording session gets
wasted.

The **legacy v2 endpoint** (`POST /v2/video/generate`, with
`character: {type: "avatar" | "talking_photo"}`) has no `engine` field at all, so
it can never reach Avatar V. Any pipeline still on v2 is capped below what the
account supports, regardless of how good the source recording was.

## Verified account facts (2026-07-24)

The founder's identity is **one avatar group**, `e0f74a0ef22147c8a8aeddf546f30bd8`,
containing 20 looks:

- **`453ce294c5ce42a48b7345c9cd13d2df`** — `avatar_type: digital_twin`,
  `status: completed`, 720×1280 **portrait**, has a real `preview_video_url`.
  This is the to-camera recording.
- **`344a0b3abfe3435da41a8820efa669e4`** — "The Man in Blue Linen by the Window",
  `avatar_type: photo_avatar`. Founder-designated, 2026-07-24.
- 18 further `photo_avatar` looks (Seattle skyline, cream sweater, whiteboard,
  microphone, blue tunic…) — prompt-generated variations on the same identity.

**Every one of those looks reports `supported_api_engines:
["avatar_v", "avatar_iv", "avatar_iii"]`.**

### Correction to the published docs

The public engine-comparison table states Avatar V is Digital Twin only and marks
Photo Avatar as unsupported. **That is not true of this account** — the photo
avatar looks are Avatar V eligible, which is consistent with the other doc page
noting that on Avatar V "photo avatars auto-select the best `instant_avatar`
sibling in their group". Do not refuse Avatar V on a photo avatar because a table
said so. **Always read `supported_api_engines` on the actual look** and believe
that instead.

Note also: `GET /v3/avatars/looks?avatar_type=instant_avatar` returns **400** on
this account — that look type is not available, so `engine.reference_look_id`
cannot be pinned to one. Cross-referencing falls back to automatic sibling
selection, and the digital twin sitting in the same group is the strong sibling
there. Keeping the twin in the group is therefore load-bearing for photo-avatar
Avatar V quality; do not "tidy it away".

### Portrait vs landscape

The twin is **portrait** (`preferred_orientation: portrait`, 720×1280). For 16:9
course intro videos a landscape-framed photo avatar look is often the better
choice, with Avatar V cross-referencing the twin for motion. Choosing a photo
avatar over the twin is not automatically the low-quality option — the engine
matters more than the look type.

## The call to make

```bash
curl -X POST "https://api.heygen.com/v3/videos" \
  -H "x-api-key: $HEYGEN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "avatar",
    "avatar_id": "344a0b3abfe3435da41a8820efa669e4",
    "script": "…",
    "voice_id": "<voice id>",
    "resolution": "1080p",
    "aspect_ratio": "auto",
    "engine": { "type": "avatar_v" },
    "motion_prompt": "warm, measured delivery; occasional open-handed gesture; stays centred"
  }'
```

Poll `GET /v3/videos/{video_id}`. Header is `x-api-key`. `avatar_id` is a **look
ID**, never a group ID.

### Choosing the expressive controls

`motion_prompt` and `expressiveness` are not interchangeable, and mixing them
wrongly is a hard validation error:

| | Avatar V | Avatar IV |
|---|---|---|
| `motion_prompt` | ✓ (video avatars + photo avatars) | ✓ photo avatars |
| `expressiveness` | ✗ **validation error if passed** | ✓ photo avatars, `high`/`medium`/`low` |

So there are two good configurations for a photo-avatar look:

1. **Avatar V + `motion_prompt`** — best motion and lip-sync. No `expressiveness`.
2. **Avatar IV + `expressiveness: "high"` + `motion_prompt`** — fallback when a
   look is not V-eligible.

**`expressiveness` defaults to `low`.** If an Avatar IV photo-avatar render looks
lifeless, that default is usually the reason.

### Mandatory pre-flight

Avatar V is opt-in per look and requesting it on an ineligible look returns 400:

```
GET /v3/avatars/looks/{look_id}   →   "supported_api_engines": [...]
```

Only pass `engine: {type: "avatar_v"}` when `"avatar_v"` is in that array. If it
is absent, fall back to Avatar IV **and say so in the hand-off** — "the video
rendered" is not the same claim as "it rendered at the quality we recorded for".

## Parameters that change the result

| Parameter | Values | Notes |
|---|---|---|
| `engine` | `avatar_v` / `avatar_iv` / `avatar_iii` | Avatar IV when omitted. |
| `resolution` | `4k`, `1080p`, `720p` | The legacy CARSI script rendered 1280×720. `1080p` is the floor; `4k` needs Avatar III on a video-avatar look. |
| `aspect_ratio` | `auto`, `16:9`, `9:16`, `4:5`, `5:4`, `1:1` | `auto` preserves source framing. Watch this with the portrait twin. |
| `motion_prompt` | free text | Body motion and hand gestures. |
| `expressiveness` | `high`, `medium`, `low` | Avatar IV + photo avatars only. Defaults to `low`. |
| `voice_settings` | `speed` 0.5–1.5, `pitch` −50…+50, `volume`, `locale` | Set `locale` for AU delivery. |
| `remove_background` | bool | Default-supported on new digital twins. |
| `output_format` | `mp4`, `webm` | `webm` for alpha compositing. |
| `caption` | object | Object form only — `caption: true` is v2 syntax and fails v3 with "Extra inputs are not permitted". Unexpected burnt-in subtitles mean you fetched `captioned_video_url`, not `video_url`. |
| `fit` | `cover`, `contain` | `cover` may crop; omit to let the server choose. |
| `callback_url` | URL | Webhook instead of polling. |

## Changing the avatar's appearance (teeth, and anything else in the face)

**A photo-avatar source with a closed mouth has no teeth to retouch.** The teeth
you see when the avatar speaks are synthesised by the engine at render time. So
"fix the teeth" is not an edit to the video and not a retouch of the existing
still — it is a change to the source image the engine conditions on.

The working loop, verified end to end on 2026-07-24:

1. `GET /v3/avatars/looks/{look_id}` → take `preview_image_url`. For this account
   it returned the full-resolution source (1536×2728), not a thumbnail.
2. Edit the image. Artlist `generate_image` in image-to-image mode with **Nano
   Banana Pro I2I** works well. Two rules:
   - **Write a minimal prompt naming ONLY the change**, and explicitly say to keep
     framing, face, glasses, hair, clothing, pose, lighting and background
     identical. Re-describing the whole image makes the model regenerate it and
     lose the likeness.
   - **Set `aspect_ratio` to match the source.** It defaults to `16:9` and will
     silently crop a portrait avatar to landscape. Use `9:16` for a portrait
     source, and `quality: "4K"`.
3. Upload the result to `https://upload.heygen.com/v1/asset` (`Content-Type:
   image/png`) → take `data.id`.
4. `POST /v3/avatars` with `{type: "photo", name, file: {type: "asset_id",
   asset_id}, avatar_group_id: <existing group>}`. Putting it in the **existing
   group** keeps one identity and keeps the digital twin available as the Avatar V
   cross-reference sibling.
5. **Poll the new look before rendering.** It returns `status: "processing"` with
   `supported_api_engines: ["avatar_iv","avatar_iii"]` — Avatar V is *absent
   while processing* and appears once `status: "completed"`. Rendering
   immediately would silently downgrade to Avatar IV. In this run the look
   completed at 2143×3840 with `avatar_v` available.
6. Render the same script on the new look and compare against the old one.

This is legitimate for the depicted person's own likeness. It is not a route for
altering someone else's face.

## Voice

v3 supports ElevenLabs-backed voices natively via `voice_id` plus
`voice_settings.engine_settings` with `engine_type: "elevenlabs"`, and rejects
the request if the voice is not compatible with the declared engine. That
replaces the older three-step workaround (ElevenLabs TTS → upload mp3 to
`upload.heygen.com/v1/asset` → `audio_asset_id`), which still works but is no
longer necessary. `audio_url` / `audio_asset_id` remain available for lip-syncing
audio produced elsewhere.

The twin carries `default_voice_id: beb782e8f2f64820abcb88e2e8d671d5`. The
founder's cloned ElevenLabs voice is `d13q7opBU6BQzFofa7oa`.

## Consent

Digital twins require the depicted person's consent before rendering; photo and
prompt avatars do not (`consent_status: null`). A twin that will not render is
often a consent state, not a bad request body.

## Failure modes that have actually cost time here

- **Staying on v2.** Renders fine, cannot reach Avatar V. This is the current gap.
- **Omitting `engine`.** Silent Avatar IV.
- **Passing `expressiveness` with Avatar V.** Validation error.
- **Leaving `expressiveness` unset on an Avatar IV photo avatar.** Defaults to
  `low`, reads flat.
- **Rendering at 1280×720.** Wastes the capture.
- **Trusting a name label.** Twenty looks share this identity, several named
  "…Digital Twin…" that are actually `photo_avatar`. Read `avatar_type` from the
  API; do not infer it from the name. A `/talking_photo/` path in
  `preview_image_url` also signals a photo avatar.
- **Assuming docs over the account.** The engine-support table is wrong for this
  account's photo avatars.
- **Short timeouts.** Generation commonly runs 10–15 minutes and can exceed it.
  Budget 15–20, and report genuine progress rather than a perpetual "composing"
  (the UNI-2219 honest-status rule in SKILL.md).

## Before a batch

Renders cost credits and a 43-course batch is a real spend surface. Render **one**
course as a reference, watch it, get founder sign-off on look + engine + motion
prompt, then batch. Record the exact engine and parameters alongside the output
so later courses match the first.
