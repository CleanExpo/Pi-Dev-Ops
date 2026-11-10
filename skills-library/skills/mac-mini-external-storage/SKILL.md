---
name: mac-mini-external-storage
description: Mac Mini only. Use when writing models, caches, worktrees, TMP, Docker data, HuggingFace, Codex runtime, or any large artifact on Phills-Mac-mini, or when Macintosh HD / internal Data is full, or when relocating files onto Storage Unit or the Mini Mini 2T SSD. Do not invoke on other machines unless /Volumes/Storage Unit with UUID 26197317-E479-4856-A823-11F9999EC1CD is mounted.
---

# Mac Mini external storage lock

Internal Data (`Macintosh HD`, `/System/Volumes/Data`) holds macOS and applications only.

**Completion criterion:** every model, cache, worktree, TMP file, and Docker blob this session creates lives on an external drive, not under `$HOME` on the internal volume.

## Two tiers (since 13/10/2026)

| Drive | Hardware | Role |
|---|---|---|
| `/Volumes/Mini Mini 2T Storage` (UUID `76BBC342-8EFB-4758-A917-2884994A95AB`) | Crucial X10 SSD, 10 Gb/s, ~700 MB/s, ~1,800 small files/s | **Hot**: TMP, package caches, models, new repos/worktrees |
| `/Volumes/Storage Unit` (UUID `26197317-E479-4856-A823-11F9999EC1CD`) | Toshiba USB HDD, 5 Gb/s, ~5 small files/s | **Cold**: archives, backups, media, legacy app data |

Never put node_modules, pnpm stores, TMP or builds on Storage Unit; that is what made installs take hours.

## Gate

1. Hostname contains `Mac-mini`, **or** `/Volumes/Storage Unit/.migration/VOLUME-UUID` equals `26197317-E479-4856-A823-11F9999EC1CD`.
2. If this is the Mini and both volumes are missing: **stop**. Do not fall back to `/tmp` or `~/.cache`.
3. If this is not the Mini and the volumes are missing: skip this skill.

## Where things go

| Kind | Destination |
|---|---|
| Agent TMP, scratch | `/Volumes/Mini Mini 2T Storage/hot/{tmp,scratch}` |
| npm, pnpm, uv, pip, yarn, Playwright, Next, Turbo, Cargo, Puppeteer | `/Volumes/Mini Mini 2T Storage/hot/caches/<tool>` |
| Docker models | `/Volumes/Mini Mini 2T Storage/hot/AI-Models/Docker` |
| HuggingFace / torch | `/Volumes/Mini Mini 2T Storage/hot/caches/{huggingface,torch}` |
| Repos / worktrees (new) | `/Volumes/Mini Mini 2T Storage/{code,worktrees}` per `ESTATE-LAYOUT.txt` (UNI-2780; moves via estate_manifest only) |
| Codex worktrees / runtime / sessions, Hermes, Claude projects | still `/Volumes/Storage Unit/Application-Data/` (not yet moved) |
| Archives, backups, quarantine | `/Volumes/Storage Unit` |

Source `~/.config/ccw-external-storage.env` before creating files; it resolves hot paths to the SSD and falls back to Storage Unit if the SSD is unplugged. GUI apps get the same values from `com.unite.storage-env`.

Default paths (`~/.npm`, `~/.cache/*`, `~/.docker/models`, `~/.codex/worktrees`, …) must remain **symlinks** onto external storage. If you find a real directory there, copy-verify-swap; never `rm` the only copy. Guard: `com.unite.storage-guard` (`~/.local/bin/unite-storage-guard.sh`). Migration records and done contract: `/Volumes/Mini Mini 2T Storage/.migration` (git repo).

The SSD has ownership ignored (every file appears owned by the logged-in user). If ownership is ever enabled, run `sudo chown -R` over it afterwards.
