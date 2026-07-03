# `.harness/` — tracked vs runtime-mutated boundary

This directory holds both **committed configuration/corpus** and **runtime state that
the swarm rewrites every cycle**. Mixing the two in git produced phantom diffs and
guaranteed merge conflicts on any branch older than one poll cycle (UNI-2250). The
rule below keeps builder PR diffs clean.

## Tracked (commit these)

- **Docs & specs** — `*.md`, `agents/*.md`, `anthropic-docs/*.md`, schema files
  (`*.schema.json`).
- **Config** — `cron-triggers.json` (rare hand-edits are intentional).
- **Seeded corpus** — `lessons.jsonl` is append-only by design and is the one
  `.jsonl` kept under version control on purpose.

## Ignored (runtime-mutated — never commit)

Enforced by the repo `.gitignore`. These are recreated at runtime, so a fresh
checkout that lacks them still boots. Do **not** `git add -f` them.

- `.harness/*.jsonl` (except `lessons.jsonl`, which predates the ignore rule and
  stays tracked)
- `.harness/swarm/*.jsonl`, `.harness/swarm/*_state.json`,
  `.harness/swarm/green_merge_counter.json`, `.harness/swarm/pr_rate_limit.json`,
  `.harness/swarm/telegram_drafts.json`
- `.harness/workspace-intel/*.jsonl`, `.harness/curator/*.jsonl`,
  `.harness/curator/state.json`
- Per-feature state: `autonomy.jsonl`, `bvi-history.jsonl`,
  `fallback-dryrun-log.jsonl`, `integration-health.jsonl`,
  `linear-pulse-state.json`, `sources_processed.jsonl`, `triage-cache.json`,
  and the other single-purpose state files listed in `.gitignore`.

## If you add a new runtime state file

Add its path to `.gitignore` **before** the first swarm cycle writes it, otherwise
it lands in a builder PR diff. When in doubt: if a file changes without a human
editing it, it is runtime state and belongs in the ignore list.

Ref: UNI-2250 (Pi-Dev-Ops mirror of the RA-1374 `.pi-ceo/` gitignore enforcement).
