# Skills Library Board

The standing board in charge of the skills library. It sits first in every /spm run: the
preflight prints its `board` line before the model reads anything else. Founder goal,
22/10/2026: work from one clean folder, stay current with the vendors, and keep the
Markdown from stalling agents.

## Seats and standing checks

| Seat | Check | Looks at | Gated when |
|---|---|---|---|
| Librarian | **home** | the canonical clone on the Mini SSD (`/Volumes/Mini Mini 2T Storage/code/skills-library`), this machine's `~/.claude` worktrees | the clone has tracked changes or `main` is behind origin; prunable or detached (leftover review) worktrees exist |
| Scout | **fresh** | installed Claude Code, Codex and Cursor CLI against npm dist-tags and Cursor's installer; the newest real Claude Code changelog entry, the Codex release feed and the Cursor CLI changelog; Anthropic's model deprecations page | any installed version is behind the latest (shown once per release line, e.g. 2.1, not for every daily patch; the trade-off is that a later patch on a shown line is not announced); a model Anthropic lists as retired, or deprecated with a set retirement date, is missing from `retired-models.txt` (a deprecated model whose date is "To be announced" still answers and is left out, as the list's generator does) |
| Gatekeeper | **md** | `CLAUDE.md`, `AGENTS.md`, `rules/` and the Markdown of every skill whose home is this library (`skills/HOMES.json`); skills owned by another repo and nested `library/` collections are counted as skipped, not scanned | any finding below |

Markdown classes the Gatekeeper reports (each has a planted-defect test in `test_board.py`):

- `gate-refused`: shell substitution around git or gh in a code block. The release gate's own detector decides, so the check cannot drift from the gate.
- `refused-cmd`: hook bypasses, force pushes, skipped permissions, ssh spellings the permission rules do not match.
- `env-read`: reading or sourcing a `.env`-style file, or a tool that dumps variables.
- `abs-path`: a path that names one machine's home folder.
- `dead-link`, `dangling-skill`, `no-skill-md`, `frontmatter`, `oversize`: things that cannot load or route.
- `retired-model`: a model ID on `scripts/retired-models.txt`.

Lines that forbid something ("never …", "do not …", "don’t …", "should not …", "cannot …") are not
counted as instructions to do it.
A requirement or idiom is not a ban ("don't forget the step with …", "never skip these steps", "don't
worry and run it with …", "to avoid conflicts run …"). Skipping hooks, checks or gates is always a ban
("never skip hooks or …", "Never skip hooks:"), and so is skipping or failing open with a means ("never
skip CI by passing --no-verify", "do not fail open with …"); "don't skip the step using …" is not. A
purpose clause keeps going through "to <verb>" ("to avoid having to run `--no-verify`, fix the hook" is
a ban). The "no" inside a flag such as `--no-edit` forbids nothing. Code blocks and list items are
forbidden only under a forbidding heading or a "Never run these:" lead-in. Under a heading, prose that
itself forbids ("Also never run these:", "The gate refuses each of these.") and an item's indented
paragraphs keep the hold; other prose ends it, as does the end of a lead-in's list.
Known limits: these are wording rules, so a line can still be read as a requirement or a ban wrongly;
each finding is shown once and can be dismissed.
`--force-with-lease` counts as a force push, because the release gate refuses it too.
Anything the Board could not read (offline, fetch failed, no files, gate detector unavailable)
is `UNPROVEN`, never clean or current.

## New versus known (founder rule, 22/10/2026)

Phill sees each finding once. Markdown findings are the same on every machine, so they are announced only on the Mini, the one clean home; other machines count them on the md line but never call them new or record them; preflight there shows them as KNOWN ELSEWHERE, never CLEAN. Versions and worktrees differ per machine and are announced where they are found. `probe` returns `new` (not shown before) and a `known` count;
only `new` items reach the founder batch. Never re-list known items to him, and never restate
problems already discussed, planned or not fixable by us. A finding that clears and comes
back counts as new again. Each case is tracked on its own (file and line), so a new case of a known kind is still new. Counts (commits behind, dirty files) are shown again only when they grow past what was already shown. Gaps are tracked by kind, so a changed number in the same gap is not new. The Board's own state (refresh failing, refresh stuck, cache old and refreshing) stays on the `board` line every run, but reaches the founder batch once, like any other gap. A shown-list that cannot be read (permissions, I/O) is named and never saved over. A damaged one is set aside as `*.bad.<time>.<pid>` by the next recorded run, which starts a new list (one re-show, nothing lost). Only a missing list counts as a first run. With no cache at all, the note says why (a failing refresh is named) and repeats until a cache exists. Without file locks (Windows) the shown-list is saved unlocked rather than not at all. A section the Board could not read never forgets what was already shown, and that holds for each Markdown part on its own (the gate detector, the retired-model list). A line with an unread part says `partial` every run; preflight counts known gaps under UNPROVEN, never CLEAN. The full detail stays in the `board` line and in `board.py report`
for the agent's own work.

## How it runs

- `scripts/board.py refresh` does the live work: version lookups, changelog, the md scan and the home check. It takes about 3 s and caches the result. On the Mini the cache always lives in `hot/state/spm/` on the SSD; with the SSD unplugged the Board says so and takes no reading. Other machines use `~/.local/state/spm/`.
- **Retries.** A reading with a gap that could close by itself (a failed fetch, an unread page, a crashed check) is retried after 1 h. A full reading, or one whose only gaps are lasting (no canonical clone here, origin not fetched offline, the retired-models list or `HOMES.json` missing or unreadable, folders or files unreadable, no Markdown found, the gate fallback), is kept for 24 h.
- **Locking.** A file lock (`board.lock`) is held for the whole refresh, so only one runs at a time and a crashed run never leaves a stale lock. A refresh past 4 minutes stops and writes nothing; one holding the lock over 10 minutes is reported as stuck. Only a 'would block' error means another refresh holds the lock; a filesystem or platform without file locks uses an exclusive marker file instead, under the same deadline; a marker left by a crash (its process gone; past 10 minutes where that cannot be asked; past 20 minutes even if its process ID answers, since a refresh cannot outlive its 4-minute deadline and the ID was reused) is cleared so the next refresh can start. A live one between 10 and 20 minutes is reported stuck. The shown-list has its own lock, so two /spm runs started together never both show the same case.
- **Gate detector.** The release gate's own detector is used only when the installed file is byte-for-byte the blob on the local origin/main (read with replace objects off); those exact bytes run, isolated. Otherwise the regex fallback runs and the md line says partial.
- `scripts/board.py probe --record --limit 5` is what preflight calls. It is offline, takes under 0.1 s and starts the detached refresh when one is due. With `--record`, only the findings it returns are marked shown; anything over the limit stays new for the next run. Without `--record` (a hand run) it shows the same but marks nothing shown.
- `scripts/board.py report` prints every finding with file:line examples. `summary` prints them readably.

## What the Board may do

- **Read, report and propose.** Board items go in the founder batch. Like every other preflight item, they never block the request.
- **Fix in passing.** When the task already touches a file that carries a finding, fix the finding there, inside that change.
- **Batch the rest.** Any other md fixes go as one library PR through the release gate. On skills-library, a push is a merge, so it waits for review.
- **Founder-only:**
  - deleting or retiring worktrees, branches or skills;
  - updating CLIs on another machine;
  - any change to hooks or permissions.

  For each, propose the exact list (paths, counts, how to recover) and wait for the yes.
- **Never:**
  - delete without that list;
  - push past a gate;
  - treat a stale or unproven reading as clean.

## Clean home

There is one canonical clone per repo on the Mini SSD (`code/<Repo>`) and one worktree folder (`worktrees/<Repo>/<branch>`). The 22/10/2026 consolidation imported every branch, stash, worktree HEAD and uncommitted change from the Mini, the MacBook and the Windows PC into the canonical clone, under `import/<machine>/…`, with snapshots in its ignored `_imports/` folder. New work starts from that clone, not from a machine's `~/.claude` checkout.
