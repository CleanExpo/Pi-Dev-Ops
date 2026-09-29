---
name: no-dead-ends
description: Use the moment you are about to write "cannot", "unable", "blocked", "not possible", "unavailable", "no way to", "would need permission", or to report a task as stopped. A stated limit is a hypothesis, not a fact. This skill converts it into a search before it reaches the human.
updated: 2026-08-18
---

# No dead ends

Almost every "I cannot" in this estate has been false. Not a lie — an unsearched assumption
stated with the confidence of a finding.

## The rule

**Before the word "cannot" reaches the human, spend one search.** One tool call. If a route
exists, take it. If none exists, report the limit *and* the routes you eliminated.

"I cannot X" is only ever acceptable as: **"X is blocked by Y; I tried A, B and C; here is what
would unblock it."**

## Measured examples, all from one session (2026-08-18)

| Stated limit | What was actually true | Cost of the route |
|---|---|---|
| "Cannot run mutation control — the classifier blocks editing the gate" | The block was on the LIVE file. A throwaway `git clone` mutates freely. It then found two surviving mutants — a real defect the live-file attempt would never have reached. | one `git clone` |
| "Independent review is unavailable, Codex is out of credits" | A free, already-benchmarked OpenRouter swarm sat in the same directory, scoring 4/4 where claude-opus-5 scored 2/4. | one script run |
| "No transcripts found" (`find` returned 0) | `~/.claude/projects` is a symlink; `find` needs `-L`. There were 3,576. | one flag |
| "estate-sync is broken" | It was correct. A livelock in a freshness guard was the cause; reading the script found it in one pass. | one `grep` |
| "The `/courses` acronym finding is false" | Checked one 20-line window. The violation was 40 lines below. Two reviewers were right; the refutation was the shallow thing. | one `grep` over the whole file |

## The routes to try before saying no

1. **Isolate instead of asking for permission.** A `git clone`, a worktree, a temp copy. Most
   denials are about the live artefact, not the operation. Mutating a sandbox harms nothing.
2. **Search the internet.** Exa, WebSearch, WebFetch. Developer docs, GitHub, Hugging Face,
   changelogs, issue threads. The API you think lacks a feature usually gained it.
3. **Read the source.** Almost every "it does not support that" dies on one `grep` of the tool's
   own code. Its `--help` is not its contract; the source is.
4. **Change the shape of the command.** A blocked chain often passes unchained (`env -C DIR cmd`
   instead of `cd DIR && cmd`). The gate that blocked a push told the exact accepted form.
5. **Use a different substrate.** Three machines on Tailscale, several model vendors, subscription
   CLIs, local models. "This one is rate-limited" is never "there is no reviewer".
6. **Split the work.** Too large for a context budget means chunk it, not skip it.
7. **Ask what the check is actually protecting.** Often the safe 90% is unblocked and only the
   last 10% is gated. Ship the 90%.

## What is genuinely a stop

Real limits exist and must be reported plainly, not worked around:

- **A safety denial on the real target.** Do not route around a classifier or a hook by
  disguising the command. Isolate instead, or stop.
- **A credential only the founder holds.** State which one.
- **A destructive or irreversible action without tested rollback.**
- **An action the constitution reserves for a human** — merges, sends, spend, production mutation.
- **Evidence that does not exist yet.** When a gate needs a proof you have not performed, the
  answer is to perform it, never to write PASS beside it.

The difference: a real stop names the specific thing and what would clear it. A false stop is a
sentence with no search behind it.

## Red flags in your own draft

If you are typing any of these, run one search first:

"cannot" · "unable to" · "not possible" · "no way to" · "blocked by" · "unavailable" ·
"would require permission" · "out of scope" · "I do not have access to" · "there is no"

And the subtlest one: **"the work has reached its edges"**. That sentence has never once been
true in this estate. There was always a documented list of open items when it was written.
