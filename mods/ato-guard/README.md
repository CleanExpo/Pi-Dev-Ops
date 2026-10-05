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

No network calls, no credentials, no settings.

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
