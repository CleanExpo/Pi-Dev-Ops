# Claude Code 2.1.288 and 2.1.289 — mod and plugin entries only

Filtered from https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md
(pulled 2026-10-06). Lines are verbatim; entries that don't concern mods or plugins are left
out. The unfiltered 2.1.287–2.1.289 sections are in `CHANGELOG-2.1.287-289.md`.

## 2.1.289

- Fixed a deny or ask rule on a nested part of a compound shell command not holding over a user-installed mod's approval on managed machines
- Improved how quickly large files open in a plugin code pane by laying the highlighted view out once at its final width
- Fixed `plugin list`, `plugin eval` and `plugin update` showing a stale copy of a plugin installed from a local folder marketplace, and hot reload for a symlinked `--plugin-dir`
- Fixed installed mods not loading in the first session after an upgrade
- Fixed a plugin's rows above the prompt showing a stale row while the Background tasks dialog was open in fullscreen
- Fixed plugin panes drawing nothing when a link used a localhost address, an `@` in its path, an uppercase host or a `file:` path
- Fixed a user-installed plugin being able to rewrite the descriptions of an organization-managed MCP server's sign-in tools
- Fixed a freeze or forced quit at launch when a plugin drew a Box with a border style the terminal does not know
- Fixed supervised and background sessions ending when a plugin's on-screen handler threw asynchronously
- Fixed sessions ending with an interface error when a plugin region with no height kept growing
- Fixed `claude plugin validate` skipping the plugin when the folder also holds a marketplace manifest
- Added `agent.spawn` for teammates, one agent id across plugin hook events, and idle and waiting states in `$.agent.list()`
- Fixed sessions ending with "unrecoverable interface error" when a value a mod's `ui.render` hook wrote made a row throw while drawn; the engine now draws its own row instead
- Fixed right-aligned content in a mod's pane or band drawing under the close mark or `[-]`, which now also keep one column in from the terminal's edge
- Fixed a mod's `Client` that fails while drawn taking down everything the mod drew around it; it now fails alone and raises `ui.fault`
- Fixed `claude plugin validate` failing an Anthropic marketplace's own plugin and listing a clean `plugin.json` in `--json`
- Fixed a mod's band that fails to draw briefly telling the cards under it to step aside
- Fixed a failed plugin component showing `Error` or nothing as its reason when the failure carried no message
- Improved the line a mod's author sees when its band or pane fails to draw: it names the mod and says nothing was drawn
- Fixed a mod's Client region staying failed for the whole session after the terminal threw while drawing it

## 2.1.288

- Added `$.ui.selection()` for mods: returns the text you last selected in fullscreen mode and, when the selection lies within one transcript row, that row
- Fixed a mod's button sometimes running a different button's action when pressed on a view drawn before Claude Code restarted
- Fixed a plugin's pane showing nothing when one `Code` element held a diff that does not parse; it now draws as plain code
- Fixed plugin LSP servers receiving literal `${user_config.*}` and `${CLAUDE_PLUGIN_ROOT}` placeholders in `initializationOptions` and `settings` instead of substituted values or manifest defaults
- Fixed a plugin's `tool.call` hook making Bash fail and file searches read the wrong folder in subagents that run in a worktree
- Fixed `git-subdir` plugin installs failing, or caching an incomplete plugin, on older git (before 2.39, e.g. Ubuntu 22.04's 2.34)
- Fixed plugins loaded with `--plugin-dir` not showing "Configure options" in `/plugin`
- Fixed background sessions ending when a plugin was reloaded or disabled while one of its timers or reads was still running
- Fixed fullscreen sessions exiting with "unrecoverable interface error" when opening the background tasks dialog while a plugin or mod showed rows above the prompt
- Fixed agent teams: a plugin-defined agent spawned by name now runs with its own prompt, tools, disallowedTools and effort instead of the defaults
- Fixed `claude plugin install` failing for GitHub-source plugins on macOS and Linux machines with no GitHub SSH key: the clone now falls back to HTTPS and prints a notice
- Fixed `owner/repo` plugin marketplaces showing only the second attempt's error when both the SSH and HTTPS fetch fail; both errors are now shown, with the transport tried first on top
- Fixed `claude plugin test` reporting mods as turned off remotely when it had only read an out-of-date saved setting
