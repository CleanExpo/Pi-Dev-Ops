# Mac Mini Autonomy Permissions

Date: 2026-05-17
Owner: Phill / Hermes CEO Operator
Status: setup-required

## Objective

Give Codex, Hermes, Claude CLI, Computer Use, Chrome, Obsidian, Plaud, and the local Pi-CEO stack enough macOS access to keep builds moving, while preserving approval gates for money, production deploys, secrets, publishing, and strategic direction changes.

## Validation Update — 2026-05-17 18:54

Current state after permissions were adjusted:

- PASS: Codex can read/write the working repos and 2nd Brain wiki paths.
- PASS: Accessibility check succeeded via `System Events` process count.
- PASS: Automation check succeeded via Google Chrome Apple Event window count.
- BLOCKED: Full Disk Access is still missing for the active Codex process. `sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db"` returned `authorization denied`.
- BLOCKED: Screen Recording is still missing for the active Codex process. `screencapture -x /tmp/codex-permission-screencap.png` returned `could not create image from display`.

Required follow-up:

1. In **System Settings -> Privacy & Security -> Full Disk Access**, enable `/Applications/Codex.app`.
2. In **System Settings -> Privacy & Security -> Screen & System Audio Recording**, enable `/Applications/Codex.app`.
3. Quit and reopen Codex after granting. macOS often does not apply TCC changes to already-running processes.
4. Re-run the validation commands below.

## Validation Update — 2026-05-17 18:56

Current state after the second permission adjustment:

- PASS: Codex can read/write the working repos and 2nd Brain wiki paths.
- PASS: Accessibility check succeeded via `System Events` process count.
- PASS: Automation check succeeded via Google Chrome Apple Event window count.
- PASS: Screen Recording check succeeded. `screencapture -x /tmp/codex-permission-screencap.png` produced a valid 2560x1440 PNG.
- PARTIAL: Full Disk Access is still not fully available to this active Codex process for direct TCC database inspection. `sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db"` still returned `authorization denied`.

Operational impact:

- Builds, repo work, browser automation, screen capture, Chrome control, Obsidian/wiki file access, and local agent orchestration can continue.
- Direct TCC database inspection remains blocked until Codex is granted Full Disk Access and restarted, or the command is run from a fully authorized Terminal process.

## Current Findings

- macOS: 26.5, Apple Silicon.
- Active apps/processes observed:
  - Codex: `/Applications/Codex.app`, bundle `com.openai.codex`
  - Terminal: `/System/Applications/Utilities/Terminal.app`, bundle `com.apple.Terminal`
  - Chrome: `/Applications/Google Chrome.app`, bundle `com.google.Chrome`
  - Obsidian: `/Applications/Obsidian.app`, bundle `md.obsidian`
  - 1Password: `/Applications/1Password.app`, bundle `com.1password.1password`
  - VS Code: `/Applications/Visual Studio Code.app`, bundle `com.microsoft.VSCode`
  - Hermes CLI running from `/Users/phill-mac/.local/bin/hermes`
  - Claude CLI running from Terminal
  - Plaud MCP running through Node/NPM
  - Computer Use client running through Codex Computer Use
- Direct TCC database read was blocked (`TCC_DB_NOT_READABLE`), so remaining grants must be confirmed manually in System Settings.

## Required macOS Privacy Grants

Grant these from **System Settings -> Privacy & Security**.

| Permission | Apps to allow | Why |
|---|---|---|
| Accessibility | Codex, Terminal, Google Chrome, VS Code, Obsidian | Click/type/control local apps, terminal panes, browser sessions, and editor UI. |
| Screen & System Audio Recording | Codex, Google Chrome, Terminal, VS Code | UI verification, screenshots, visual QA, browser testing, and voice workflow QA. |
| Input Monitoring | Codex, Terminal, Google Chrome, VS Code | Keyboard automation and terminal/browser control. |
| Full Disk Access | Codex, Terminal, VS Code, Obsidian | Repo access, 2nd Brain/wiki sync, local logs, TCC-state diagnostics, and automation evidence. |
| Files and Folders | Codex, Terminal, VS Code, Obsidian | Desktop/Documents/Downloads/External folders as needed. |
| Microphone | Google Chrome, Codex, Terminal | ElevenLabs/voice tests, Plaud/Whisper-style flows, browser voice session checks. |
| Camera | Google Chrome only if needed | Optional; only for future avatar/video/live-agent tests. |
| Automation | Codex -> System Settings, Terminal, Chrome, Obsidian; Terminal -> Chrome/Obsidian | Apple Events control for browser, Obsidian, and app orchestration. |
| Local Network | Codex, Terminal, Google Chrome | Localhost agents, Hermes gateway, Pi-CEO API, CRM dev server, MCP services. |

## Keep These Gated

Do not remove approval requirements for:

- 1Password item reveal/export.
- Production deploys, DNS changes, environment variable mutation, database migrations.
- Paid spend, ad publishing, email/SMS broadcast, public social posting.
- Changes to business direction, endpoint routing, or ownership boundaries.
- Credential creation or deletion.

Recommended gate text:

> I have enough local permission to prepare this action. This changes production, spend, credentials, or strategic direction. Phill approval required before execution.

## Manual Setup Steps

1. Open each Privacy & Security pane.
2. Add or enable the apps listed above.
3. Quit and reopen the affected apps after each grant:
   - Codex
   - Terminal
   - Google Chrome
   - Obsidian
   - VS Code
4. Re-run the validation checks below.

## Validation Checks

Run from Terminal after permissions are granted:

```bash
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
  "select service, client, auth_value from access where client in ('com.openai.codex','com.apple.Terminal','com.google.Chrome','md.obsidian','com.microsoft.VSCode') order by service, client;"
```

Run in Codex after restart:

```bash
python3 - <<'PY'
from pathlib import Path
checks = [
    Path.home() / "Library/Application Support/com.apple.TCC/TCC.db",
    Path.home() / "2nd Brain/2nd Brain/Wiki/index.md",
    Path.home() / "Pi-CEO/Pi-Dev-Ops",
]
for p in checks:
    print(p, "readable=" + str(p.exists()))
PY
```

## Operating Rule

Local automation may proceed autonomously when it is reversible, local-only, and evidence-producing.

Anything irreversible, external, paid, credential-bearing, or production-affecting remains approval-gated by Phill.
