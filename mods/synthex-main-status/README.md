# synthex-main-status

Claude Code mod that puts a status line under the prompt while **CleanExpo/Synthex
`main` CI is red**. Synthex main sat red for two weeks (SYN-1205 / SYN-1211) without
anyone noticing; this makes it visible in every Synthex session.

Linear: RA-7907 · Mods docs: `docs/reference/claude-mods/`

## What it does

Only in a session whose repo remote is `CleanExpo/Synthex` (any other repo: nothing
runs, no timer). At start and then every two minutes it runs, read-only:

```bash
gh run list --repo CleanExpo/Synthex --branch main --limit 1 --json conclusion,status,displayTitle,url
```

| Latest run on main | Status line |
|---|---|
| `failure`, `cancelled`, `timed_out` | `main is RED: <title, up to 50 chars>` |
| `success` | cleared |
| in progress, gh missing / not signed in / timed out, non-zero exit, no runs, bad output, other conclusions | `main CI status unknown (<reason>)` |

A failed read never clears the line. Once the first read has finished, no line
means green. Before that (the first read runs in the background at session start
and can take up to 20 s), no line means "not checked yet". The line is updated
only when it changes. It writes nothing to GitHub or anywhere else.

Needs `gh` signed in on the machine (`gh auth status`).

## Check and test

```bash
claude plugin validate mods/synthex-main-status
(cd mods/synthex-main-status && claude plugin test)
```

## Install

From the `pi-dev-ops-mods` marketplace (see `mods/mc-lane/README.md` for marketplace
setup and auto-update):

```bash
claude plugin install synthex-main-status@pi-dev-ops-mods
```

Try it in one session first, from a Synthex checkout, pointing at this repository's copy:
`claude --plugin-dir /path/to/Pi-Dev-Ops/mods/synthex-main-status`.
