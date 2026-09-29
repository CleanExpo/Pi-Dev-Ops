# The challenge loop

Branch-only detail. SKILL.md carries the four rules that must never page out; this file
carries the mechanics. Read it when you reach phase 4.

## Why Codex and not another Claude

Model diversity is the whole point. Measured in this estate: Codex has caught CRITICAL
defects that a Claude suite had already blessed 12/12 green, and has FAILed branches at
identical SHAs that a same-vendor Claude reviewer PASSed. A reviewer that shares the
author's weights shares the author's blind spots and agrees with them fluently.

Two contaminants defeat that diversity if you let them:

- `~/.codex/AGENTS.md` opens *"Claude Code receives the same shared context on this
  workstation."* An out-of-the-box challenger inherits the author's doctrine.
- `~/.codex/config.toml` wires the `second-brain` MCP — the same corpus `nexus-recall`
  read in phase 1. "Independent research" over the author's own corpus is not independent.

`challenge.sh` handles both for design briefs (`--ignore-user-config`, scratch `-C`).
Code-shaped briefs must run in the repo and therefore *do* inherit its `AGENTS.md` —
record that in the ledger rather than pretending the run was clean-room.

Note: `--ignore-user-config` drops `config.toml` but Codex still loads its skills catalogue
(you will see a "skills context budget" warning). That is cosmetic here; the doctrine and
MCP contamination are what matter.

## What the challenge brief contains

Exactly four things:

1. The goal verbatim, as he dictated it
2. The five intent slots
3. The bar
4. The brief

**Withheld, deliberately:** the research narrative, the alternatives considered and
rejected, and any statement of confidence. Those are the contaminants — hand them over and
the challenger reviews your reasoning instead of your plan, and agrees with it.

Plus the instruction block: return one JSON object matching the output schema; every
`claim` must quote a brief line verbatim or be discarded; list in `unchallenged` what you
did not examine and why.

## Register — the thing that gets runs killed

Frame the task as **independent QA of a proposed plan**: *"Confirm the plan does what it
claims, and identify any case class it does not cover."*

Never "attack it", "break it", "exploit", "find the vulnerability", "verify by attacking".
OpenAI's classifier kills on the **framing, not the subject** — it has fired on a plain
content-quality guard — and a killed run writes no report at all. When a kill happens,
**read the partial log before retrying**: twice it has contained a real defect.

## Running a round

```bash
~/.claude/skills/waterline/scripts/challenge.sh <round-dir> [design|code] [repo-path]
python3 ~/.claude/skills/waterline/scripts/anchor.py <round-dir> [prev-round-dir]
```

`challenge.sh` prints `CLASS=…` and never decides a verdict. `anchor.py` computes the
brief hash, discards unanchored findings, detects a stall, and exits 0 only when no
blocking finding survives.

Never run two challenges in parallel — quota is the shared ChatGPT plan window, not API
credits, and `parallel-delegate` forbids it.

## Failure ladder

| `CLASS=` | Meaning | Do |
|---|---|---|
| `VERDICT` | schema-valid report on disk | run `anchor.py` |
| `NO_VERDICT` | empty or unparseable report | re-emit **once**, quoting the parse error. Never author the report yourself. Second failure → `UNCONVERGED` |
| `QUOTA` | 429 / usage limit | Stop. It is the plan window — waiting is the fix, buying API credits does nothing. `kimi-k3` via OpenRouter only as an explicit downgrade, stamped `challenger: kimi-k3 (DEGRADED)`. A weaker challenger is not the same evidence |
| `CLASSIFIER_KILL` | non-zero exit, no report | **Read the partial log first** and harvest any finding in it. Re-frame in the QA register, retry once. Two kills means the framing is not the problem — stop |
| `TIMEOUT` | >900s | `UNCONVERGED` |

**Silence, timeout, or crash is not a pass.** The only PASS is a schema-valid report with
zero surviving blocking findings.

## Rounds

- **Exit = a fresh run over the current brief returning zero anchored P0/P1.** That is the
  only convergence there is.
- **The bound of 4 is a budget guard, not an exit.** On exhaustion, emit the brief stamped
  `UNCONVERGED` with every open disagreement quoted from both sides. A round count never
  authorises a finish line.
- **Round N+1 runs only if round N's blocking finding actually changed the brief.** A
  finding you reject with reason is a *disagreement*, not an iteration — stop, and print
  both positions verbatim in a `CODEX SAYS` block. Never auto-reconcile.
- **A clean round 1 is a legitimate result.** Report it with `unchallenged[]` attached so
  the reader can tell clean from lazy. Forcing three rounds trains a challenger to
  manufacture findings to justify its turn. Observed on the first real run: Codex emitted
  `{"verdict":"PASS","blocking_findings":[]}` and then revised itself to FAIL with two real
  defects — the lazy pass is its opening move, which is exactly what `unchallenged[]` and
  the empty-boundary warning exist to expose.
