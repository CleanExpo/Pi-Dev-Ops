---
name: mac-mini-external-storage
description: Mac Mini only. Use when writing models, caches, worktrees, TMP, Docker data, Ollama, HuggingFace, Codex runtime, or any large artifact on Phills-Mac-mini, or when Macintosh HD / internal Data is full, or when relocating files onto Storage Unit. Do not invoke on other machines unless /Volumes/Storage Unit with UUID 26197317-E479-4856-A823-11F9999EC1CD is mounted.
---

# Mac Mini external storage lock

Internal Data (`Macintosh HD`, `/System/Volumes/Data`) holds macOS and applications only.

**Completion criterion:** every model, cache, worktree, TMP file, and Docker blob this session creates lives under `/Volumes/Storage Unit`, not under `$HOME` on the internal volume.

## Gate

1. Hostname contains `Mac-mini`, **or** `/Volumes/Storage Unit/.migration/VOLUME-UUID` equals `26197317-E479-4856-A823-11F9999EC1CD`.
2. If this is the Mini and the volume is missing: **stop**. Do not fall back to `/tmp`, `~/.cache`, or `~/.ollama`.
3. If this is not the Mini and the volume is missing: skip this skill.

## Where things go

| Kind | Destination |
|---|---|
| Ollama | `/Volumes/Storage Unit/AI-Models/Ollama` |
| HuggingFace / torch | `/Volumes/Storage Unit/ccw-agent/caches/huggingface` |
| Codex worktrees / runtime / sessions | `/Volumes/Storage Unit/Application-Data/Codex/` |
| Docker models / VM | `/Volumes/Storage Unit/AI-Models/Docker` and `Application-Data/Docker/` |
| Agent TMP, npm, Playwright, uv | `/Volumes/Storage Unit/ccw-agent/` |

Source `~/.config/ccw-external-storage.env` (or `/Volumes/Storage Unit/ccw-agent/env.sh`) before creating files.

Default paths (`~/.ollama/models`, `~/.codex/worktrees`, …) must remain **symlinks** onto Storage Unit. If you find a real directory there, copy-verify-swap; never `rm` the only copy. Reclaim script: `/Volumes/Storage Unit/.migration/reclaim-uni2591.sh`. Guard: `com.unite.storage-guard`.

Do not load `homebrew.mxcl.ollama`. Live server is `com.unite.ollama-serve` with `OLLAMA_MODELS` on Storage Unit.
