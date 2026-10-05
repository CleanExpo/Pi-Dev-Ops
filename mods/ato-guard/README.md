# ato-guard

Claude Code mod that guards taxpayer data in sessions on the **ATO repository**.
The real repository is [`CleanExpo/ATO`](https://github.com/CleanExpo/ATO). The mod also
treats any repository whose name has `ato` as a whole word (e.g. `ato-ai`, `ATO-portal`)
as in scope; names that merely contain the letters (`pi-ceo-operator-mcp`,
`SC-Generator`, `…-Calculator`) are not. Everywhere else it does nothing.

Linear: RA-7908 · Mods docs: `docs/reference/claude-mods/`

## What it does (in the ATO repository only)

| | |
|---|---|
| **Mask** (`hooks/mask.ts`) | Every tool result is scanned before Claude reads it. TFNs (8–9 digits, or `ddd ddd ddd`), ABNs (11 digits, or `dd ddd ddd ddd`), BSB `ddd-ddd` + account number (6–10 digits) and `Bearer …` / `xero…token=…` values become `[masked:TFN]`, `[masked:ABN]`, `[masked:BANK]`, `[masked:TOKEN]`. Numbers inside longer runs, ISO dates, phone numbers and invoice numbers (`INV-000123`) are left alone. |
| **Block** (`hooks/guard.ts`) | Refused without running: Bash that writes to `api.xero.com` (`-X/--request POST\|PUT\|PATCH\|DELETE`, `-d`, `--data*`, `--json`, `-F`); any `mcp__*xero*` tool whose last name segment does not start with `get`, `list`, `search` or `read`; Bash or MCP calls that mention SBR or lodgement together with a write verb (post, put, patch, submit, send, create, delete, lodge). Reads pass through untouched. Bash segments run by local text tools (`git`, `grep`, `cat`, `ls`, `sed`, …) are not checked, so commits and searches that mention lodgement still work. |
| **Audit** (`hooks/audit.ts`) | One JSON line per masked or denied call in `~/.ato-guard/audit.jsonl`: `{ at, session, tool, decision, counts }`, where `decision` is `masked:<n>` or `denied`. Never the tool's input, output or matched text. Past 3 MiB the file moves to `audit-<date>.jsonl`. A failed audit write never affects the tool call. |

No network calls, no credentials. One optional setting: `ATO_GUARD_ALLOW_MODS` (below).

## Refuse tool-rewriting mods (in the ATO repository only)

`hooks/policy.ts`, hooked on [`plugin.register`](../../docs/reference/claude-mods/reference.md)
(fires once for each hooks module about to load; `e.uses.events` lists what it hooks; a hook
returns `{ refuse: reason }`). In the ATO repository, ato-guard refuses every other
non-built-in mod — any tier: `user`, `prepend` or `append` — whose events include any of:

| Event(s) | Why |
|---|---|
| `tool.call`, `tool.check`, `tool.describe` | can rewrite, answer, approve or re-describe tool calls, so could undo the masking or the write blocks |
| `prompt.*` (`prompt.submit`, `prompt.section`, `prompt.context`, …) | can rewrite what Claude reads |
| `classic.PreToolUse`, `classic.PostToolUse` | settings-hook events on tool calls |
| `engine.create` | can change the mods API other mods receive |

Wildcards are expanded: `*`, `tool.*`, `classic.*`, `engine.*` and `prompt.*` all count. Everything
else (`session.*`, `agent.spawn`, `ui.render`, `turn.*`, …) loads. Built-in mods always load.
The user's debug log names the refusal as `<mod>: refused by ato-guard: in the ATO repository …`.

**mc-lane.** mc-lane hooks `tool.call` (to read tool names and timings), so the rule refuses it
— on purpose — unless it is on the allow list. `ATO_GUARD_ALLOW_MODS` is a comma list of plugin
names or `<name>@<marketplace>` ids; **unset, it is `mc-lane`**. Set it to an empty string to
refuse mc-lane too. A refusal is only `{ refuse: reason }`, so the docs offer no allow list of
their own; this one is ato-guard's, and it exempts a mod from the `tool.call` rule **only**: an
allowed mod that also hooks `tool.check`, `prompt.*`, `*`, … is still refused. `plugin.register`
gives a mod's name and id as the mod itself states them, so the allow list trusts the name; put
`ATO_GUARD_ALLOW_MODS` in managed `env` (below) so a user settings file cannot widen it.

**Fails closed in scope.** If the check throws or times out while the session is known to be in
the ATO repository, the mod being checked is refused (`.catch` handler). Outside it, or when the
repository cannot be read, the check passes everything.

### What `plugin.register` can see — read before deploying

The docs and the types Claude Code 2.1.289 writes say a module's judges are "the plugins
admitted before it and the binary's". A hook on `plugin.register` therefore sees **only the mods
that load after it**; a mod already admitted is never re-judged. The order is (events → "The
order mods run in"): built-in guard and managed `prependPlugins`, then other organization mods,
then mods users install, then `appendPlugins`, then other built-in mods.

So ato-guard installed from the `pi-dev-ops-mods` marketplace — a GitHub source, which the docs
count as a **user's** mod even when managed `enabledPlugins` turns it on — is best effort only:
it judges just the user mods that happen to load after it, and `prependPlugins` skips it.
To make the rule airtight ato-guard must count as the organization's and be **first** in
managed `prependPlugins`.

### Deploy so it runs first and cannot be bypassed (managed settings — not applied anywhere yet)

The docs' conditions for an organization's mod: managed `enabledPlugins` sets it `true`; managed
settings name its marketplace as a **directory on the machine by absolute path**
(`extraKnownMarketplaces`); the marketplace lists it by relative path so it loads in place.
Device management copies a marketplace directory, writable only by an administrator, to every
machine, e.g. `/Library/Application Support/ClaudeCode/unite-group-managed/`:

```text
unite-group-managed/
├── .claude-plugin/marketplace.json   # "name": "unite-group-managed", plugins: ato-guard, mc-lane → ./plugins/<name>
└── plugins/
    ├── ato-guard/                    # copy of mods/ato-guard
    └── mc-lane/                      # copy of mods/mc-lane
```

Then `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS):

```json
{
  "extraKnownMarketplaces": {
    "unite-group-managed": {
      "source": { "source": "directory", "path": "/Library/Application Support/ClaudeCode/unite-group-managed" }
    }
  },
  "enabledPlugins": {
    "ato-guard@unite-group-managed": true,
    "mc-lane@unite-group-managed": true
  },
  "prependPlugins": ["ato-guard@unite-group-managed", "sec-default@builtin"],
  "pluginConfigs": {
    "cc-plugin-sec-default@builtin": {
      "options": { "allowManagedModsOnly": true }
    }
  },
  "disableSideloadFlags": true,
  "env": { "ATO_GUARD_ALLOW_MODS": "mc-lane" }
}
```

What each key does (per `docs/reference/claude-mods/admin.md`):

* `extraKnownMarketplaces` + `enabledPlugins`: make ato-guard (and mc-lane) the organization's mods.
* `prependPlugins`: ato-guard first, the built-in guard second. Setting this list **replaces the
  default**, so `sec-default@builtin` must be named or the built-in guard does not load.
  Repository settings can never set it.
* `pluginConfigs` → `allowManagedModsOnly` (only under the id `cc-plugin-sec-default@builtin`):
  the built-in guard refuses every mod that is not the organization's or built in. Note this
  also refuses the GitHub-installed copies of mc-lane, fleet-guard and synthex-main-status on
  that machine; ship any you still want through the managed directory as well.
* `disableSideloadFlags`: rejects `--plugin-dir` / `--plugin-url`, so a mod cannot be side-loaded.

Check on a test machine with `claude --debug`: the debug log line `hooks module
ato-guard@unite-group-managed loaded` must say `tier prepend`. `tier user` plus `prependPlugins
names … which is not an enabled managed plugin with a hooks module; skipped` means the directory
conditions are not met.

Residual gaps the docs state: `claude --safe-mode` runs with no installed mods (ato-guard's
masking included), and if the hooks worker crashes three times every non-built-in mod is off for
that session. Neither lets another mod run while ato-guard is off.

## Check and test

```bash
claude plugin validate mods/ato-guard
claude plugin test mods/ato-guard
```

## Install

From the `pi-dev-ops-mods` marketplace in this repository (see `mods/mc-lane/README.md`
for adding the marketplace and turning on auto-update):

```bash
claude plugin install ato-guard@pi-dev-ops-mods
```

It is safe to install on every machine: outside the ATO repository it is inert.

## Try it in one session

```bash
cd ~/path/to/ATO && claude --plugin-dir /path/to/Pi-Dev-Ops/mods/ato-guard
```
