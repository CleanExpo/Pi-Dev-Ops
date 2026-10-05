# Claude Code mods — vendored developer docs

Pulled 2026-10-04 from the official Claude Code docs (`code.claude.com/docs/en/plugins/mods/*.md`)
and the `anthropics/claude-code` CHANGELOG. Docs are written against **Claude Code v2.1.289**
(stated at the top of `reference.md`). Mods shipped in **v2.1.287** ("Added Claude Mods: plugins may
now modify deeper behavior"); launch post: https://claude.com/blog/claude-code-mods (1 Oct 2026).

These are copies. Before relying on a detail, check the live page — mods are days old and the
changelog is moving fast (2.1.288 and 2.1.289 are mostly mod fixes).

| File | Source page | What it covers |
|---|---|---|
| `overview.md` | /plugins/mods/overview | What a mod is, where mods run (CLI, Desktop Code tab, `-p`, Agent SDK, Remote Control), mods vs hooks/skills/MCP |
| `create.md` | /plugins/mods/create | First mod, reload/validate loop, getting the build's types |
| `events.md` | /plugins/mods/events | Observe / rewrite / answer tool calls, prompts, turns; matchers; mod ordering |
| `api.md` | /plugins/mods/api | `$` API: commands, tools, `$.model`, timers, cross-session messages, fs/process/http |
| `interface.md` | /plugins/mods/interface | Panes, band above the prompt, buttons, fields, `$.state` / `$.store` |
| `gallery.md` | /plugins/mods/gallery | Element gallery with sample code |
| `reference.md` | /plugins/mods/reference | Full events, API methods, render sites, elements by surface, limits, settings |
| `test.md` | /plugins/mods/test | `claude plugin test`, stubbing, no network/session needed |
| `troubleshoot.md` | /plugins/mods/troubleshoot | Refusal messages, debug log |
| `admin.md` | /plugins/mods/admin | Managed settings: `allowManagedModsOnly`, `allowManagedHooksOnly`, `disableAllHooks`, org mods |
| `plugins-overview.md` | /plugins | Plugin packaging (mods ship inside plugins) |
| `CHANGELOG-2.1.287-289.md` | anthropics/claude-code CHANGELOG | Launch + two follow-up releases |

Refresh: `for p in overview create interface gallery events api reference test troubleshoot admin; do curl -fsSL -o $p.md https://code.claude.com/docs/en/plugins/mods/$p.md; done`

Integration plan for Mission Control, Synthex and ATO-AI: `docs/specs/claude-mods-integration.md`.
