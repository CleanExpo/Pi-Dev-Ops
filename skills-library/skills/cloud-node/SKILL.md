---
name: cloud-node
description: How an ephemeral managed Claude Code container (claude.ai/code, the mobile and web app, a GitHub Action) joins the estate as a first-class node instead of working blind. Use at the start of any cloud session, when a cloud session needs work another machine must finish, or when something present on every workstation appears to be missing. Triggers on "am I in the estate", "why can't I see the skills", "run this on the mini", "hand this off before the container dies".
version: 1
updated: 2026-08-31
allowed-tools: Read, Grep, Glob, Bash
---

# cloud-node — the fourth surface

## The problem this fixes

An estate session running in a managed container starts with **almost nothing**. Measured
2026-08-31 in a live container: `~/.claude/skills/` held **2 entries, not 356**. No
gauntlet, no fleet, no farm, no claim ledger, no memory. `fleet.py probe` did not list it
at all, so the fleet table reported three nodes while a fourth surface was doing real work.

That is the estate's recurring failure in its purest form — **work happening where the
other machines cannot see it** — and it compounds: the container is reclaimed after
inactivity, so anything not pushed is not merely invisible, it is gone.

## Join, at the start of every session

```bash
bash ~/skills-library/skills/cloud-node/scripts/cloud-pull.sh
```

Read-only. It reports the checkout, HEAD, how far behind `origin/main` it is, which node
the registry thinks this is, unread mail, and — explicitly — what is **not** available
here. It never pulls on its own: a fetch that rewrites the tree under a running session is
worse than a stale tree you were told about.

If there is no checkout:

```bash
git clone --depth 1 https://github.com/CleanExpo/skills-library ~/skills-library
```

## What this node can and cannot do

Stated flatly because each has been assumed at least once, and an assumed capability
burns a session before it is disproved. All verified in a live container on 2026-08-31.

| | |
|---|---|
| **GitHub** | Yes. This is the only channel to the rest of the estate. |
| **Tailscale** | **No.** It can never be an `ssh` dispatch target, and cannot reach `mini-ts` or `win-ts`. |
| **Codex CLI** | **No.** No binary, no `~/.codex`, no `OPENAI_*`. Signing in to Codex on a workstation does not change this. Dispatch Codex work to the Mini. |
| **OpenRouter** | **No key.** `curl` returns `000`. The free-model tier is machine-side only. |
| **estate-sync** | **No.** It installs a LaunchAgent or a Task Scheduler job; this container is ephemeral and has neither. `cloud-pull.sh` is the substitute. |
| **Peer messaging** | Sometimes. `ListAgents` shows other live sessions when there are any; usually there are none. Do not build on it — use `estate-mailbox`. |
| **Compute** | Real and usable: 4 cores / 16 GB measured. Good for analysis, review prep, and repo work. |

## Getting work to a machine

This node cannot dispatch over SSH, so it hands work over asynchronously:

```bash
python3 ~/skills-library/skills/estate-mailbox/scripts/mailbox.py \
    post --to mini --kind review-request --ref <sha> --body-file packet.md
git -C ~/skills-library add estate/mailbox/mini.jsonl && git -C ~/skills-library commit -m "..." && git push
```

**The push is the delivery.** A message written and not pushed is exactly the failure
mode this skill exists to remove, one layer up.

For a Codex critic specifically: prepare the packet here, post it to `mini`, and let the
Mini run `fleet.py dispatch --node mini`. Codex there is always `--sandbox read-only`, and
the job must **print to stdout** — the sandbox blocks `apply_patch`, so a prompt ending
"write your findings to a file" completes successfully and writes nothing.

## Before the container dies

It is reclaimed after inactivity, without warning. Anything that matters must have left:

1. **Push every branch.** An unpushed commit here is not "local work", it is deleted work.
2. **Post a `handoff` message** for whichever node continues.
3. **Say what was not finished**, in the mailbox, not only in chat — the chat does not
   survive either.

## The four surfaces this node must not touch

Carried verbatim from `gauntlet-pair`, and they bind here identically:

- `~/.claude/skills/` — read freely, **never edit mid-run**. Three machines commit there.
  A wanted skill change goes on the board as a proposal.
- `~/.claude/projects/*/memory/` — same; `MEMORY.md` is a shared index and last write wins.
- **Merge and deploy gates** — this node never merges to `main` and never approves a
  production deploy, however good the board looks. Human gates stay human gates.
- **Another surface's project** — never read into it, never "just fix" something there.

## Related

`estate-mailbox` (the channel) · `fleet-compute` (the registry; this node is `cloud`,
`local_only`, runtimes deliberately empty) · `estate-sync` (what this substitutes for) ·
`gauntlet-pair` (the AAA+ ladder and the shared-surface rules)
