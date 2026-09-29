---
name: dream
description: Use to curate machine-local memory from recent session transcripts — invoked as /dream, /dream status, or /dream apply 1,3. Reads ~/.claude/projects/**/*.jsonl from the last 24h, dedupes by session id, excludes the current session and sessions that produced nothing durable, and proposes memory additions and supersessions with a verbatim quote as evidence for each. Also use when asked whether memory curation has run recently, or when a dream heartbeat is stale. Every proposal is [synthesised] and may never be cited as evidence for a gate.
---

# dream — curate memory from what actually happened

`/dream` reads recent transcripts and proposes changes to `~/.claude/memory/`. It proposes;
the operator disposes. Run it with `python skills/dream/dream.py` (deployed:
`~/.claude/skills/dream/dream.py`).

```
dream.py              scan the last 24h, write a report and a run record
dream.py status       last run; RAISE past 36 hours
dream.py apply 1,3    append the chosen proposals; comment out what they supersede
dream.py --selftest   prove the redactor and the marker set discriminate
```

## The rule that travels with this skill

**Every proposal is `[synthesised]`, never `[observed]`.** It is inferred from a transcript —
a record of what was *said*, not a reading of a live system.

> **A synthesised memory may never be cited as evidence for a gate.**

If a gate needs to know something, it must check the system, not consult a memory of a
conversation about the system. Memory is a hint that tells you where to look. The moment a
synthesised line is treated as a verified fact, every downstream check inherits a claim nobody
ever tested — and it will read exactly like a checked one. Quote the memory, then go and look.

## What it does, and why each step exists

1. **Reads `~/.claude/projects/**/*.jsonl` modified in the last 24h.** Older transcripts have
   already had their chance to be curated.
2. **Dedupes by session id.** This box writes one session under two project keys
   (`C--Users-Disaster-Recovery-4` and `-Users-phill-mac`). A naive glob counts it twice, and
   every proposal drawn from it inherits doubled weight.
3. **Excludes the current session.** A dream that reads its own transcript mines its own
   reasoning as evidence. Self-contamination by the act of measuring has already happened on
   this box. Set `CLAUDE_SESSION_ID`, or pass `--exclude-session`.
4. **Excludes sessions with no durable artefact** — no commit, no branch, no file write.
   Fourteen sessions on 2026-08-03 ended cleanly having called nothing. Synthesising memory
   from sessions that did no work manufactures signal out of an absence of signal, which is the
   `feedback_loop` defect in a new costume.
   **Also excludes slash-command payloads and pasted documents.** A `/nexus <brief>` invocation
   is stored as a user message, so mining it means re-proposing *the instructions this agent was
   given* as though they were corrections the operator volunteered. That is rule 3's failure in
   a second costume. Found in the first real run, which proposed 20 items, most of them command
   envelopes; after this filter, 9, all genuine.
5. **Compares what survives against `~/.claude/memory/`** — corrections given, preferences
   repeated, facts worth keeping, memories now stale or contradicted, duplicates.
   The comparison **excludes `dream-*` files**, and matches against individual memory *lines*.
   Both were bugs in the first real run: `dream-report.md` lives in the memory directory, so run
   two read run one's own proposals back as existing memory and tagged everything `supersede` —
   the tool treating its own output as evidence, which is the third costume of the same fault.
6. **Proposes as a numbered list**, each with a **verbatim quote** as evidence and the file it
   would touch. A proposal without a quote is an opinion.
7. **Auto-applies only typos and index repairs.** Everything else waits for
   `/dream apply 1,3` or `/dream apply all`.
8. **Writes exactly one run record.** See the heartbeat.

## The heartbeat — three outcomes, never two

Appended to `~/.claude/memory/dream-runs.jsonl`, one line per run:

| outcome | meaning | how it is known |
|---|---|---|
| `ran-proposed-N` | ran, found N things | a record saying so |
| `ran-nothing-to-propose` | ran, found nothing | a record saying so |
| `did-not-run` | never executed | **the ABSENCE of a record** |

The third is never self-reported, because a process that failed to run cannot report that it
failed to run. `dream.py status` raises when the newest record is older than 36 hours, and
raises differently when there is no record at all.

**This distinction is the whole point.** One exit code covering both "worked" and "nothing was
there" is exactly the defect that hid the ideas drain through ten consecutive green runs. The
record carries the outcome; the exit code only says whether the run itself completed.

## Structural safety — properties, not promises

- **No delete path. No overwrite path.** There is no code in `dream.py` that removes a memory.
  `apply` appends a new line and comments the old one out, so the history of a memory stays
  readable. Removal is the operator's instruction, executed by the operator.
- **Redaction happens before any write.** Transcripts are a secrets-rich surface — that is why
  they are gitignored, after `autogit` swept them into commits. A credential-shaped match is
  replaced with `[REDACTED <shape>]`; only the *name* of the shape is ever recorded. The matched
  value is never returned, logged or stored.
- **No network. No repo writes.** `dream.py` opens no sockets and writes exactly one directory:
  `~/.claude/memory/`.
- **Unattended runs propose only.** A scheduled run writes the report and the record and applies
  nothing beyond typos.

### On the redaction patterns being a copy

`dream.py` carries its own copy of `scripts/secrets_check.py`'s pattern set rather than importing
it. Three reasons, all structural: that script scans *git-tracked files* rather than arbitrary
text; on a hit it files a Linear ticket and fires a Telegram alert, which breaks "no network";
and once this skill is deployed to `~/.claude/skills/dream/` the repo is not present to import
from. Keep the two lists in sync by hand. `--selftest` asserts the copy still detects each shape
**and** leaves clean text untouched, so a redactor that silently matched nothing cannot pass.

## Spec vs runtime state

| | where | tracked |
|---|---|---|
| **spec** — this file, `dream.py` | `skills/dream/` | yes, in `MANIFEST`, under drift enforcement |
| **runtime state** — reports, run records, memories | `~/.claude/memory/` | **never** |

Same taxonomy as `config/harness/` versus `.harness/`. The machine-local side is deliberately
outside the repo: it contains transcript-derived content, and the repo is not the place for it.

## Scheduling

**After editing this file, re-deploy** (`python fence/deploy_skills.py`). Otherwise `--check`
goes red for a reason that is not drift — the machine copy is simply behind the repo. That
happened on 2026-08-04, and per-file naming is what made it readable in one glance: it reported
`SKILL.md  differs` while `dream.py` was silent, so the cause was obvious rather than a hunt.

**Run `dream.py install-task` rather than hand-writing the wrapper.** The wrapper
`~/.claude/dream-task.cmd` cannot itself be tracked — it holds this machine's python path and
home directory, so a committed copy would be wrong on every other box, and a tracked file that
is wrong everywhere but here is worse than none. The **generator** is tracked instead: this
skill is in `MANIFEST` and travels via the directory copy, so the wrapper always has a canonical
source. Rebuilding the box is `deploy_skills.py` then `dream.py install-task`.

Windows, so `schtasks`, not cron. **Registered and verified firing on `phill-desktop`,
2026-08-04**, daily at 03:00, via a machine-local wrapper `~/.claude/dream-task.cmd`.

### The missed-run policy, and why `did-not-run` alone would get muted

A 03:00 task on a desktop that may be switched off simply **misses**. `did-not-run` would then
be correct and useless — firing most mornings for something that is not a fault. A freshness
check that cries wolf is one that gets switched off, and then a real staleness gets ignored.

Two fixes, both required:

1. **`StartWhenAvailable`**, so a missed window runs at the next opportunity instead of being
   skipped. `schtasks` **cannot set this** — it needs PowerShell:
   `Set-ScheduledTask -TaskName claude-dream -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable)`
2. **`status` names the cause**, and only some causes are faults:

| cause | meaning | raises? |
|---|---|---|
| `machine-was-unavailable` | scheduler has no record of it ever running — window missed | **no** |
| `task-failed` | it ran and returned a real error code | yes |
| `task-ran-but-wrote-nothing` | clean exit, no record — a silent fault | yes |
| `unknown` | scheduler unreadable; no cause may be assigned | yes |

⚠️ `SCHED_S_*` values are **statuses, not failures**, reported in the same field as an exit code
(`267011` = `TASK_HAS_NOT_RUN`, `267009` = `RUNNING`). The first version of the classifier read
`267011` as "returned 267011 — this IS a fault", i.e. it called a task that had never run a
failure. That is exactly the cry-wolf behaviour, and only the machine-unavailable arm of the
control caught it — the task-failed arm passed identically before and after the fix.

⚠️ **The quoting trap, which produced a registered task that silently did nothing.** The home
path contains a space (`C:\Users\Disaster Recovery 4\`). `schtasks` stores `/TR` unquoted, so at
run time it tried to execute `C:\Users\Disaster` and returned `-2147024894`
(`ERROR_FILE_NOT_FOUND`). The task queried as present, with a plausible *Next Run Time*, and had
never once succeeded. Register against the 8.3 short path instead, which contains no spaces:

```
schtasks /Create /TN "claude-dream" /TR C:\Users\DISAST~1\CLAUDE~2\DREAM-~1.CMD /SC DAILY /ST 03:00 /F
```

**Registering it is not evidence it runs.** Force one execution and prove the record appeared:

```
schtasks /Run /TN "claude-dream"          # then confirm dream-runs.jsonl gained a line
schtasks /Query /TN "claude-dream" /FO LIST /V | findstr "Last Result"   # 0, not -2147024894
```

The first registration here passed every check except the one that mattered. The line count going
3 → 3 is what exposed it — which is the heartbeat catching a scheduled task that was never really
scheduled, the exact failure it exists for.
