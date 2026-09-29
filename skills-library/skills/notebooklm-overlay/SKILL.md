---
name: notebooklm-overlay
description: "Apply the locked-in Unite-Group editorial overlay system to any NotebookLM-generated video (Video Overview output, daily briefings, audio overviews rendered as video). Use AFTER video-use produces a base render; this skill applies a post-process editorial overlay pass that gives every NotebookLM video a distinctive house identity. Triggers on \"NotebookLM video\", \"daily briefing video\", \"audio overview\", \"video overview\", or any video with NotebookLM as the source aesthetic. Brand-agnostic: takes a beats JSON config (window/title/body per beat), renders editorial-serif cards (Charter italic title, Charter regular body, hairline rule, warm-cream card on dark hairline at the top edge) and composites them onto the bottom-third with 300ms cubic fade in/out. Composes with the video-use skill — video-use cuts and renders the base, this skill polishes."
---

# notebooklm-overlay

The locked-in Unite-Group house identity for every NotebookLM-source video. Use this skill **after** `video-use` produces a base render to add the editorial overlay polish that distinguishes a Unite-Group NotebookLM video from a generic NLM output.

## When to use

Fire this skill in any of these cases:
- Editing a NotebookLM Video Overview output
- Editing a daily briefing video (the Pi-CEO daily briefings are NLM-generated)
- Editing any video whose source aesthetic is NotebookLM's hand-drawn-illustration style
- The user mentions "NotebookLM video", "daily briefing video", "audio overview", "video overview"

## Composition with video-use

```
video-use → preview_base.mp4   (rendered with --no-subtitles)
   ↓
notebooklm-overlay → preview_final.mp4   (editorial cards composited)
```

**Important:** Render the `video-use` base with `--no-subtitles`. The bold-CAPS subtitles in video-use's default `bold-overlay` style fight the editorial overlay tonally — pick one or the other. The editorial overlay wins for NLM videos because the cards carry the copy.

`master.srt` from video-use is still useful — keep it as a sidecar for YouTube / LinkedIn upload.

## Usage

```bash
# Author beats.json aligned to the EDL output timeline
cat > beats.json <<'EOF'
{
  "beats": [
    {"window": [0.5, 6.5],   "title": "May 2026", "body": ["Pi-CEO running 11 portfolio businesses, zero-touch."]},
    {"window": [8.0, 19.5],  "title": "Swarm Activated", "body": ["Guardian  ·  Builder  ·  Scribe  ·  Click"]},
    {"window": [21.0, 47.5], "title": "May 2026 — What Shipped", "body": [
      "98 features across 12 sprints.   85 / 100 health score.",
      "Marathon-4:  a flawless six-hour autonomous run."
    ]},
    {"window": [49.0, 61.0], "title": "Powered by Claude", "body": ["1-hour prompt cache  ·  −80% tokens  ·  pre-compact hook"]}
  ]
}
EOF

# Render
~/Developer/video-use/.venv/bin/python ~/.claude/skills/notebooklm-overlay/overlay.py \
  --input preview_base.mp4 \
  --beats beats.json \
  --output preview_final.mp4
```

The script uses video-use's venv because it ships PIL pre-installed there. If you don't have video-use installed yet, install it first (`uv sync` inside `~/Developer/video-use/`).

## Locked house style (do not vary without explicit user approval)

| token | value |
|---|---|
| card BG | rgba(250, 249, 246, 235) — warm cream, ~92% opaque |
| top rule | rgba(40, 40, 40, 220), 2px hairline |
| title | Charter italic 42pt, near-black |
| body | Charter regular 24pt, soft dark gray |
| position | bottom-third (y = video_height − card_height) |
| card height | 220px (≈20% of 1080p frame) |
| pad-x | 96px (5% of 1920) |
| fade | 300ms cubic in / 300ms cubic out at each window edge |

The visual identity is locked. The CONTENT (beats / titles / body lines / windows) is per-video.

## beats.json schema

```json
{
  "beats": [
    {
      "window": [start_s, end_s],   // numbers, seconds in the OUTPUT timeline
      "title": "string",             // serif italic, single line
      "body": ["string", "string"]   // 1–3 lines, serif regular
    }
  ]
}
```

Notes:
- `window` is in OUTPUT seconds (after video-use's cut), not source-clip time.
- Card auto-fits — keep body lines under ~70 chars each at 24pt to stay inside the 1920×220 card.
- For 4–5 beat reels, expect window durations of 6s (HOOK/UPGRADES) through 26s (METRICS).

## Brand-agnostic by design

The same renderer handles any portfolio brand or client by swapping the `beats.json` content. Don't introduce per-brand colors / fonts unless the user explicitly asks for a brand-specific variant — the locked house style is the point.

If a future variant is needed (e.g., a particular client demands their own typography), fork `overlay.py` into a new skill (e.g., `notebooklm-overlay-acme`), don't mutate this one. Lock-in here means stable.

## Anti-patterns

- Don't apply subtitles in the base render — they fight the editorial overlay.
- Don't position the card outside the bottom-third — NotebookLM puts its content in the upper 2/3.
- Don't use card BG with <80% opacity — body text becomes unreadable over busy NLM frames.
- Don't add per-brand colors / logos without an explicit user request — that breaks the "brand-agnostic" lock.
- Don't re-encode the audio when applying overlays — `-c:a copy` preserves the loudnorm pass from video-use.
