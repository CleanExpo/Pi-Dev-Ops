---
name: skill-watch
description: Daily check on everything the estate took from outside Claude Code (third-party skills, npm tools, watched repos) plus the context budget and each new Claude Code release. Use when adding any outside skill or tool ("install this repo", "add these skills"), when reading or acting on the daily skill-watch report, or when asked "are we bloating the context" / "is this skill still needed".
updated: 2026-09-17
---

# skill-watch

**What it does.** Every morning a small robot on this MacBook checks the things we installed from
outside and tells us what changed. It never installs, updates or deletes anything by itself.

- Script: `scripts/skill_watch.py`
- Registry: `external-skills.json`. This is the single list of outside skills, their pinned
  versions, and repos we are watching.
- Schedule: LaunchAgent `com.unite.skill-watch`, daily at 06:17. It runs
  `skill_watch.py run --review`.
- Reports:
  - `~/.local/state/skill-watch/<date>.md` plus `latest.json` and `history.jsonl`
  - a copy in the vault at `Outcomes/skill-watch/<date>-skill-watch.md`

## What the daily run checks

| Check | How | Flags when |
|---|---|---|
| Context budget | `claude plugin details` over a symlink view of `~/.claude/skills` | always-on tokens grew; MEMORY.md over 17.1KB |
| Outside skills | `git ls-remote` vs pinned SHA, `npm view` vs pinned version | upstream moved |
| Claude Code | latest release vs `cli.reviewed_version` | a release nobody has reviewed yet |
| Watchlist | `git ls-remote` vs last run | a candidate repo got new commits |

- **A check that could not run is listed as "could not check".** It makes the exit code 2 and
  is never shown as "no change".
- **With `--review`,** one bounded `claude -p` run reviews the flagged items and writes a
  proposal into the report.
  - Limits: Sonnet model, read-only tools plus web, $2 cap.
  - It proposes. It does not apply anything.

## Adding an outside skill (every time)

0. **Its passport will say what you recorded.** Every skill, local or vault, gets a generated
   Capability Passport (below). A vault skill with no `review` or no 40-char `pinned_sha` here
   is `UNREVIEWED` and refused by `skill_shelf.mjs activate`.
1. **Review it first.** Use a subagent, read-only, with the repo cloned in the scratchpad.
   Check for hooks, scripts, network calls, settings edits, and overlap with existing skills.
2. **Install only if it earns its place.** Prefer merging new rules into an existing skill
   over adding a second skill (see `unslop`).
3. **Record it.** Add an entry to `external-skills.json` with `repo`, `path`, `pinned_sha` or
   `npm` + `pinned_version`, `installed`, and `review`.
4. **List it in both catalogs:** `README.md` and `index.md` (the 2-place rule in `skills/CLAUDE.md`).
5. **Declined or later.** Add the repo to `watchlist` with the reason, so it is not re-reviewed
   from scratch.

## Acting on a flag

- **Upstream moved:** read the compare link.
  - If the change is wanted and safe: copy the new files, re-run any gate the skill has, then
    `skill_watch.py pin <name>`.
  - Otherwise: leave the pin and note why in the entry's `review`.
- **New Claude Code release:** read the release notes.
  - Name skills the release now does natively.
  - Prove it with `claude plugin eval <skill>` (it compares with and without the skill; pass
    `--no-publish`).
  - A near-zero gap makes the skill a **retirement candidate**. Retiring is Phill's call:
    move it to `deprecated/` and take it out of both catalogs.
  - Then run `skill_watch.py pin claude-code`.
- **Context grew:** shorten the listing (`description`) of the biggest skills first. The
  report lists them.
- **MEMORY.md over target:** compaction needs Phill's OK.

## Traps

- `claude plugin details` needs the plugin name (`estate-view`). Without it the command fails,
  and the report says so.
- Claude Code auto-updates. That is why the release check compares against
  `reviewed_version`, not the installed version.
- Caliper (edonadei/caliper) was reviewed on 17/09/2026 and not adopted.
  - It runs agents with permission prompts off.
  - It copies the login token to disk.
  - `claude plugin details` and `claude plugin eval` already cover its two jobs.

## Capability Passports

`scripts/capability_passport.py` builds one passport per skill (local and vault) from that
skill's own `SKILL.md` and nothing invented: name, description, `allowed-tools`, `model`,
`owner` / `owner_role` (else `HOMES.json`), declared `capabilities` plus its `index.md` router
phrases, this registry's review and pin, and test records the tool wrote itself. Each passport
pins the sha256 of its `SKILL.md` and is checked against `capability-passport.schema.json`
(a stdlib validator that refuses any schema keyword it does not implement).

```
python3 scripts/capability_passport.py generate --validate   # -> ~/.local/state/skill-watch/passports.json
python3 scripts/capability_passport.py record <skill> -- <test command>   # trusted test record
python3 scripts/capability_passport.py activate <skill> --capability "<phrase>" --available-models opus,sonnet
```

- Risk: no `allowed-tools` (inherits every tool) or unrestricted `Bash` is high; scoped Bash,
  write, web, agent or MCP tools are medium; read-only tools are low. A `provider/model` id is
  an API-key lane: always refused.
- Conflicts: one capability phrase claimed by two different owners is listed and refused.
- Test records: a PASS whose exit code, output-log hash, recorder or source hash does not hold
  is `FAKE_PASS`. Records are integrity-checked, not signed.
- `activate` is simulated: it writes a receipt to `activation-receipts.jsonl` and changes nothing.
- The daily run regenerates passports and flags conflicts, API-key lanes, unreviewed outside
  skills and schema failures. It never installs or removes a skill.
- Tests: `python3 tests/test_capability_passport.py`; each of the six refusals has a sabotage
  in `skills/enforcement-loop/install/positive_control.py` that must turn it red.
