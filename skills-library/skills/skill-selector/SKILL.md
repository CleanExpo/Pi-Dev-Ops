---
name: skill-selector
description: The skill library's check-out / check-in loop. Use BEFORE any multi-step task when the right skills are not obvious, and whenever a task needs a skill that is not installed. Search first (skill_shelf.mjs find), pull only what the task earns (checkout from the vault, or pull a reviewed outside repo into it), use it, then check it in when the task is done. Never read the full skill catalog in the main context.
argument-hint: "<the task in plain language>"
allowed-tools: Read, Grep, Agent, Bash(node *skill_shelf.mjs *)
---

# skill-selector — search, pull, use, check in

**The problem.** The library holds several hundred skills (`ls skills | wc -l` for today's count). Reading the catalog to pick one costs more
than most tasks. Skills loaded "just in case" fill the working context with rules the task
never needed. And a skill installed for one job stays installed for every job after it.

**The loop.** One tool, four verbs. Nothing else scans the catalog, and nothing stays pulled
in after the task ends.

```
node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs find "<the task in plain words>"
node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs checkout <name>
node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs checkin <name> | --all
node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs pull <registry-name>
```

Search comes from `sorcerai/skill-router` (MIT, vendored unchanged in `scripts/vendor/`).
The only new code is the pull / checkout / checkin / overrides wrapper around it.

## 0. Name the phase first, then pull only that phase's skills

Work moves through these phases in order. Name the one you are in, check out its entry-point,
and check it in when the phase ends — the next phase's skills are not loaded until it starts.
Skip a phase only when its output already exists (an accepted brief, an approved spec).

| Phase | Question it answers | Entry-point(s) |
|---|---|---|
| 1 Intent | What does the founder actually want? | `capture-intent` (Mission Control box) · `/waterline` (ramble → challenged brief) · `grill-me` (stress a sketch) |
| 2 Decide | Should we, and is it one session's work? | `/judge` · `/wayfinder` (too big or foggy) · `ceo-board` (strategic) |
| 3 Spec | What exactly gets built, and how is done proven? | `/spm` (runs `engineering-requirements` at step 7a) · `superpowers:writing-plans` (spec → steps) |
| 4 Bar | What does "good" beat? | `gauntlet-loop` (named exemplar) · `gauntlet-ship` (launch: a production gate per item) |
| 5 Build | Make it, test first | `superpowers:test-driven-development` · UI: `mobbin-ui-patterns` then `impeccable` · bugs: `superpowers:systematic-debugging` |
| 6 Prove | Can each check fail, and is the claim true? | `control-design` (before a check exists) · `proof-discipline` (before any "green/done") |
| 7 Review + release | Independent eyes, receipt, draft PR | `pr-release-gate` (its runner picks the reviewer lane) · repo gates: `ci-quality-parity` (RestoreAssist) · go-live: `/readiness-architect` |
| 8 Done / handoff | Is it provably done, or where does it stop? | Done gate (`rules/done-gate.md`, `donectl`) · `session-handoff` · `/resume-from-handoff` |

Order disputes resolve to this table: `/readiness-architect` is a release-phase check, not a step
before the build; `capture-intent` and `/waterline` are alternative front doors to the same
phase. More than 5 skills inside one phase means the phase holds two tasks — split it.

## 1. Search first (`find`)

- Run `find` before a multi-step task, before any `/nexus` fan-out, and the moment you think
  "I need a skill for X". Skip it only when the always-loaded router (`index.md`) already
  names the skill in one hop.
- Type the task the way a person would say it, not two keywords. The index scores the
  router's trigger phrases, so "write the failing test first then refactor" finds `tdd`
  even when the word "tdd" never appears.
- It prints the top 5 only (`--limit`, max 20). It never prints the catalog.
- A query that is exactly a router phrase ("SEO", "campaign", "decision") returns that
  row's entry point first, even when a sub-skill carries the word in its name. Anything
  else ranks on score alone.
- Before every search it returns any checkout older than 24 hours, so a crashed session
  cannot leave skills pulled in.

## 2. Pull only what the task earns

| `source` in the result | What to do |
|---|---|
| `active` | It is already installed. Load it with the Skill tool. |
| `vault` | `checkout <name>`, then load it with the Skill tool. Claude Code sees the new folder without a restart, but not instantly: about 40 seconds on 18/09/2026 (the harness announces "The following skills are available"). For a one-off read, `Read` the printed path instead and skip the checkout and the wait. |

- Load a skill when its step is next, not before. Mark the rest "on demand".
- More than 5 skills for one task means the task is two tasks. Decompose it.
- Load the canonical entry-point only. Entry-points dispatch their own sub-skills.
- A name clash is refused: a hand-written local skill always wins over a vault copy of the
  same name. The tool prints the vault path if you still need the upstream version.

## 3. Use it, then check it in

- When the task is done: `checkin --all` (or `checkin <name>` per skill).
- `checkin` only ever removes a symlink that this tool created, that sits directly in
  `~/.claude/skills`, and that resolves into the vault. Anything else is refused and left
  alone. It uses `unlink`, never `rm -rf`, so it cannot remove a directory even by mistake.
- A loaded skill body stays in the conversation until compaction. Nothing can pull it back
  out. So for a heavy skill, run it in a subagent (`context: fork`, or an Agent call) so its
  body never lands in the main context at all. That is the real check-in.

## 4. Outside skills (GitHub, skills.sh, Hugging Face): vault, never install

An outside skill never goes straight into `~/.claude/skills`. It goes into the vault
(`~/.claude/skill-vault/`, machine-local, not listed, not synced), and is checked out per task.

1. Review it first, read-only, from a scratchpad clone. That is `skill-watch` step 1.
2. Add an entry to `~/.claude/skills/skill-watch/external-skills.json`:
   `name`, `repo`, `path` (folder inside the repo), `pinned_sha` (40 chars), `review` (what
   was read, when), `"vault": true`, and `exclude` for anything the review rejected.
3. `pull <name>`. It refuses without a review, without a full SHA, or if the fetched commit
   is not the pinned one. It copies files only: no scripts run, symlinks are dropped.
4. `find` now sees it. `checkout` per task. `checkin` when done. `skill-watch` keeps
   watching the pin every morning.

Worked example: `mattpocock` (reviewed 18/09/2026). 25 shipped skills sit in the vault at
zero listing cost. `wizard`, `git-guardrails-claude-code` and everything in `in-progress/`
are excluded by the registry entry.

Remote search: `DISABLE_TELEMETRY=1 npx skills find "<query>"` (Vercel's CLI) searches the
public registry. Treat a hit as a candidate for step 1, never as something to `add`.

## 5. The listing: only the router keeps a full description

Every installed skill's description is loaded on every turn, up to a budget. Over budget,
Claude Code drops descriptions from the least-used skills, in an order nobody chose.

`overrides` fixes the order. Router entry-points (every backticked name in `index.md`) and
the gates the model must reach on its own (`merge-gate`, `task-completion-gate`, `dead-checks`,
`supabase-write-gate`, `claim-verifier`, `adversarial-review`, `spec-development`) keep a full
description; add more with `--keep a,b`. The long tail becomes `name-only` (the Skill tool
still works for them; `find` supplies the description when it is needed). It never sets `off`
or `user-invocable-only`. Applied on the MacBook 18/09/2026: 340 active, 67 full, 248
name-only, 25 already hidden, about 18,700 listing tokens back.

```
node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs overrides            # dry run, prints the plan
node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs overrides --write    # backs up settings.json first
```

`settings.json` is per machine and not synced, so run it on each machine (bootstrap).

## 6. Keeping the library findable (CI guards)

Three checks run in `estate-checks.yml` and locally; a description edit that breaks routing
fails there, not on someone's next task.

| Check | What fails it |
|---|---|
| `node --test scripts/test_router_eval.mjs` | a router row whose own phrase no longer returns it in the top 5; an exact phrase not pinning its entry point; a paraphrase regressing |
| `python3 scripts/check-skill-listing.py` | an empty description; a display name that differs from the folder; an entry point over 500 chars; a router row pointing at a skill not in the tree |
| `python3 scripts/check-skill-fork.py` | a SKILL.md of 16 KB+ with neither `context: fork` nor a reason in `scripts/skill-fork-manifest.txt` |

`node scripts/skill_families.mjs` is the read-only family report: name stems shared by 3+
skills, the router entry point heading each, `NO-HEAD` where there is none. A family with
no head is where one word returns five siblings; merging or retiring is a founder call.

## Never

- Run an outside repo's install or link script against `~/.claude/skills`. The link script
  in mattpocock/skills does `rm -rf` on any non-symlink of the same name (its line 56).
- `npx skills remove -g`. It finds skills by scanning the folder, not its lock file, so it
  would target every hand-written skill here.
- Scan `README.md` in the main context to choose a skill. Use `find`, or dispatch a
  throwaway sub-agent that runs `find` and returns names only.

Relates to: `skill-watch` (review, registry, daily pin check), `nexus` (calls `find` before a
fan-out), `context-cockpit` (session-level context audit), CLAUDE.md §6 (the Library).
Tests: `node --test scripts/test_skill_shelf.mjs` (7 checks, fixture HOME, touches nothing real).
