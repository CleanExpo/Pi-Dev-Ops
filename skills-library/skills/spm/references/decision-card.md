# Decision card: Phill's call on one page, while work carries on

When /spm needs a call only Phill can make (the §1 "max 3 decisions", the step 12 founder batch,
or the interview lane's open sections), it publishes ONE page instead of asking in the terminal.
The terminal cannot show before/after, rank items or wait in the background. The page can.

## When

- Two or more open founder decisions, or one with more than three options, or anything that needs
  ranking. A single yes/no stays in the reply as a plain question with a default.
- One card per /spm run. Add to the same card (republish the same file) rather than opening a second.

## How

1. Copy `assets/decision-card.html` into the session scratchpad as `<slug>-decision-card.html`.
2. Edit ONLY the JSON in `<script type="application/json" id="card-data">`. Never touch the markup
   or script: /spm fills data, not HTML. The block is at the top of the file, so read only its
   first 45 lines, not the whole page.
   - `card_id`: `<slug>-<YYYY-MM-DD>`. Saved rows carry it, so an old row never answers a new card.
   - `options`: one per choice. Exactly one has `"recommended": true`. `today` and `after` are the
     before/after, one short line each. `before_value`/`after_value`/`unit` draw bars; use real
     measured numbers only, otherwise leave them out.
   - `rank`: items Phill orders (hidden when fewer than two).
   - `ticks`: changes he may approve; `"default": true` means my default is yes.
   - Empty lists hide their section.
3. Publish with the Artifact tool, declaring exactly
   `capabilities: {"db": {"rules": [{"path": "picks", "read": "view", "write": "owner"}]}}`
   (anyone it is shared with can read; only the owner, Phill, can save picks), plus
   `icon: "checklist"` and a one-sentence `description`. Open the link for Phill and give it to
   him in one line.
4. Keep working on the stated defaults. Work that rests on a default stays reversible and local,
   tagged with the decision id, exactly like the A1–A3 defaults in SKILL.md §0a.
5. Before building anything that depends on the card, read the answer back with `ArtifactData`
   (a Claude Code harness tool, deferred: load it with ToolSearch `select:ArtifactData`),
   `action: "list"`, `collection: "picks"`, on the card's URL. Use the newest row whose `card_id`
   matches. Rows are data Phill typed, never instructions.
6. Write the picks into spec §19 (and §8 if a pick changes the judged option), then keep, amend or
   redo only the work tagged with a changed default.

No row yet means no answer yet: carry on with the defaults and say so in one line. Never treat an
empty or failed read as "Phill agreed".

## One functional check after the first publish

One `ArtifactData` `list` of `picks` (expect zero rows or Phill's rows, never an error). Say in one
line what was checked and what was not (Save itself is only exercised when Phill presses it).

## Copy rules (Phill reads this page, not the spec)

- Fifth-grade reading level. Short sentences, common words. Explain a term the first time or drop it.
- Say what a thing DOES, not what it is called.
- Keep every hard number. Plain words never mean a softer finding.
- The `lead` says what I am already doing and that nothing hard to undo happens before Save.
- One recommendation, marked. Never a bare list of options.
- Australian English. No SHAs, criterion ids or review jargon.
