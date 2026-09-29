---
name: fleet-compute
description: "Use BEFORE any heavy multi-agent, corpus-mining, research or batch task to split the work across the whole Nexus fleet instead of one machine. Probes every node for real free capacity and which agent runtimes actually authenticate there, then dispatches each job to the node that fits. Standing default per founder directive 2026-07-29: using one machine while another is idle is the failure, not the safe choice."
version: 1
updated: 2026-07-29
---

# fleet-compute — run the estate on all of it

**Founder directive, 2026-07-29:** *"Use the compute from both macbook, and mac mini to
assist the processing… when I get the PC connected, that also needs to be added in. This
needs to be an automation within our harness."* Splitting across nodes is the default, not
an optimisation you reach for when something is slow.

## The one command

```bash
python3 ~/.claude/skills/fleet-compute/scripts/fleet.py probe
```

Prints cores, memory, load, free cores and usable runtimes per node, plus fleet total.
Run it before deciding where work goes. Never assume a node is up — the Windows box has
been offline for nine days and a plan that assumed it would have silently under-delivered.

## The fleet as it actually is

| Node | Host | Reach | Usable agent runtime | Hard constraint |
|---|---|---|---|---|
| macbook | local | always | Claude + Codex | your session runs here; also the only node that can run Claude non-interactively |
| mini | `mini-ts` | Tailscale SSH | **Codex only** | Claude CLI **cannot** authenticate over SSH — the login keychain is GUI-only and `launchctl asuser` is denied. Verified 2026-07-29. |
| windows | `win-ts` | Tailscale | none declared yet | `phill-desktop`, offline since ~2026-07-20. Probe it, then fill in `runtimes` in `NODES`. |

Three other Tailscale peers (`bron-docker`, `home-laptop`, `homelaptop`) have been offline
140+ days. Ignore them unless they come back.

## How to split work

**Route by data locality first, capacity second.** Moving a 1.4 GB session corpus across the
wire to a machine with two spare cores is worse than analysing it in place. The Mini holds its
own Claude and Codex transcripts, its own worktrees, and its own review history — questions
about *the Mini's* state belong on the Mini.

**Route by runtime second.** Anything needing Claude runs on the MacBook. Anything that is
read-only shell forensics, grepping, or cross-checking runs equally well as Codex on the Mini,
which frees the MacBook for the work only it can do.

**Keep the MacBook for synthesis.** Remote nodes return findings; the reconciliation, the
adversarial pass and the founder-facing write-up happen where the conversation is.

## Dispatch

```bash
# write the job prompt to a file first — it can be as long as you like
python3 ~/.claude/skills/fleet-compute/scripts/fleet.py dispatch \
        --node mini --prompt-file /tmp/job.md
python3 ~/.claude/skills/fleet-compute/scripts/fleet.py collect
```

`dispatch` copies the prompt over, launches `codex exec` detached under `nohup` so it
survives the SSH session closing, and records the job in `~/.claude/fleet-jobs/`.
`collect` pulls output back and marks each job COMPLETE or RUNNING.

**Codex is always launched `--sandbox read-only`.** Never `--dangerously-bypass-approvals-and-sandbox`
— a bypassed run is not valid gate evidence and has to be re-run anyway. See
[[subagent-codex-sandbox-required]].

**Never ask a dispatched job to write its own report file.** `--sandbox read-only` blocks
`apply_patch`, so a prompt ending in "write your findings to /tmp/report.md" produces a job that
runs to completion, refuses the write, and leaves you with a missing file that looks like a
crash. Verified 2026-07-29: a corpus audit burned 231,091 tokens, completed correctly, and wrote
nothing. **Have the job print everything to stdout** — `dispatch` redirects stdout on the remote
side outside the sandbox, so it is captured either way. The redirect works; the agent's own file
writes do not.

Two other things the sandbox blocks on the Mini, both of which return "operation not permitted"
rather than an error you would notice: `ps` and `crontab -l`. Anything depending on those comes
back unverified, so ask for `launchctl` inspection instead.

For interactive fan-out on the MacBook itself, use the Workflow tool or parallel `Agent`
calls; this skill is for reaching *other machines*.

## Adding a node

One entry in `NODES` in `scripts/fleet.py`: host alias, shell, home, runtimes, notes. Then
`probe` it and only declare a runtime after you have watched it return output. Declaring a
runtime that has never produced a result is the wired-but-never-exercised pattern that this
estate keeps paying for — see [[wired-but-never-exercised-falsepositive-class]].

For the Windows box specifically: the shell entry is already `powershell -NoProfile -Command`,
but that is **unverified** — nothing has run there. Confirm whether it answers on OpenSSH with
PowerShell or needs WSL before trusting it.

## The trap this skill was built around

`ssh host zsh -lc "<script>"` **does not work** when the argv is passed programmatically.
`ssh` joins its trailing arguments into a single remote command string, so `zsh -lc` receives
only the first word and everything after the first `;` executes in the login shell instead.
The symptom is quiet and ugly: some fields come back correct and others come back empty, so
the result looks like a partly-unavailable machine rather than a broken call. `fleet.py`
quotes the whole script as one token to avoid it.

That bug was caught by running the probe and reading the numbers — the Mini's memory value
had landed in the core-count column. **Always read the probe output rather than assuming a
zero means an idle machine.** A broken query and a quiet node look identical.
See [[proof-discipline]].

## Related

[[nexus-mesh]] · [[mini-pull-needs-gui-keychain]] · [[mini-codex-review-node-live]] ·
[[subagent-codex-sandbox-required]] · [[persistent-subagents]]
