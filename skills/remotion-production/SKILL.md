---
name: remotion-production
description: Use when a Remotion video job needs production gates, render evidence, output discipline, and pass/fail validation before it can be called shippable.
owner_role: Producer
status: remotion-wave-1
intents: remotion-production, video-production, render-gate
---

# remotion-production

Owns the production safety gate for `/remotion-video`.

## Requirements

- Use `remotion-studio/render/one-shot.ts` for production packets.
- Render through `remotion-studio/render/render.ts` only after dry-run passes.
- Require audio in production unless the operator explicitly marks a silent draft.
- Run post-render ffprobe validation and reject silent or clipped renders.
- Keep MP4s in `remotion-studio/output/` or external storage; never commit large generated videos.

## Evidence

Write under `.harness/remotion/<jobId>/`:

- `production-packet.json`
- `script.md`
- `preflight-report.md`
- `render-command.sh`
- `render-report.md` when render is attempted

## Verification checklist

- [ ] Typecheck passes.
- [ ] Dry-run packet exists.
- [ ] Render command is reproducible.
- [ ] Final report states PASS/FAILED with concrete reasons.
