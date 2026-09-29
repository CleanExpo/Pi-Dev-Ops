# Deliver (D7) + vault write-back + watch-mode

## Executive Read — inherited, delta only

Open every non-trivial run with the nexus Executive Read. SSOT (fields, template, ban-list):
`~/.claude/skills/nexus/references/orchestration-playbook.md` §'G7 — Executive Read'.
≤120 words, plain language, decision-first. Obey the G7 register ban-list PLUS the deep-loop
terms {proposer, aggregator, MoA, gap ledger, lane} — say the plain-language thing
('we checked it against a second independent reviewer').

## Report structure (below a `--- detail ---` line)

1. Scope + the framed topic (as an outcome).
2. Findings by perspective — every load-bearing claim carries `{source URL, tier}`; `unverified`
   tags kept, never load-bearing.
3. Consensus vs divergence — the defended divergence, or 'no non-consensus insight found'.
4. Open questions the swarm could not close — the REMAINING gap ledger (honesty about the edge
   of knowledge).
5. Method footer — rounds run + stop reason (saturation vs cap vs budget vs HARD_STOP); the
   ACTIVE freshness lane per round ('Exa' / 'WebSearch — Exa 402' / 'WebSearch — Exa absent');
   spend; judge flip-downgrades.

A `partial` run is labelled at the TOP ('partial — stopped after round 2 of 3, reason: <guard>').

## Vault write-back (`save:` — default `vault`)

The vault CLAUDE.md sanctions exactly one agent write-back: an **Outcomes note**. Write the full
report to `~/2nd Brain/2nd Brain/Outcomes/YYYY-MM-DD-<slug>.md` with frontmatter
(`type: outcome`, topic, freshSince, lane, rounds, spend, gapsRemaining). Never invent a new
top-level vault folder. Refresh indexes by RUNNING the generator —
`python3 "$HOME/2nd Brain/2nd Brain/_system/okf-index.py" "$HOME/2nd Brain/2nd Brain"` — never a
hand-appended index line (generated indexes clobber hand edits). `save:here` prints only;
`save:off` skips. Cited sources already in `Sources/` are reused, never re-scraped; pushing NEW
sources into `Sources/` stays an explicit `source-ingest` run.

## Watch-mode (`watch:` — composes with existing schedulers, never reimplements one)

Two surfaces (memory `feedback_scheduled_tasks_two_surfaces` — they are distinct):
- **`watch:6h`** → the built-in `/loop` skill (in-session self-pacing). Fragile by design: it
  dies with the session. Fine for a working day, wrong for standing coverage.
- **`watch:daily|weekly`** → the `schedule` skill (cron cloud routine). A session does not live
  for days; only the cron surface survives. Caveat: interactively-authenticated claude.ai
  connectors (Exa included) may be ABSENT in headless runs — those re-runs are WebSearch-tier by
  default and must say so (rung-0 in `exa-and-integrity.md`).

**Composition requirement:** the re-run must arrive as the TEXT prompt `/deep-loop <topic> …`
(which routes to the read-this-file-inline path). `Skill(deep-loop)` errors by design
(`disable-model-invocation: true`) — verify the first interval fires correctly before declaring
a watch armed.

**Incremental freshness:** a replayed command string is static, so never trust a literal
`fresh-since:` in it. At the START of each re-run, read the persisted last-run timestamp (stored
beside the report/signature file) and derive `fresh-since` from that; write the new timestamp
after the run.

**Daily spend share:** each watch re-run checks cumulative spend for the day (persisted beside
the signature) against the ~$15/day estate ceiling's share for this watch; when exhausted, skip
the re-run and log — a skipped run is cheaper than a blown ceiling.

**Edge-triggered pings (memory `feedback_alert_noise_edge_trigger` — zero tolerance for repeat
pings).** After each re-run, compute a NORMALISED synthesis signature (the DECISION line + the
verified-claim set, lowercased, volatile numbers/dates stripped — the SAME normalisation the
saturation test uses) and persist it beside the report. Ping ONLY when the signature DIFFERS
from last run — a changed decision, a new verified claim, or a flipped divergence. If nothing
material changed, log and stay SILENT. The ping is one line: what changed + the new DECISION +
the report link. Never re-send an unchanged finding.
