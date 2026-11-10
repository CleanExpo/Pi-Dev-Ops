# Interview lane: Phill's North Star, principles and decision rules, in his words

Use when Phill says "interview me", or asks for his North Star, principles, guidelines or decision
frameworks. Output: ONE vault page, `Wiki/founder-operating-code.md`, which /spm §4 and every
harness read instead of each grounding somewhere different. No approved version existed on
22/10/2026; the only North Star file was agent-written and RestoreAssist-only.

## Where things live

- Vault root `R`, resolved without guessing:
  - `SPM_BRAIN` set: `R=$SPM_BRAIN` (the same variable `scripts/journal_event.py` honours).
  - Otherwise use the same order `journal_event.py` uses, so every /spm write lands in one place:
    `$HOME/2nd-brain` if it holds `2nd Brain/_system/brain.js`, else `$HOME/2nd Brain`. Both
    checkouts exist on the MacBook today (same remote); the order, not the first glob match, decides.
    Any other match and neither of those: `UNPROVEN: vault ambiguous (<matches>)`, write nothing
    until `SPM_BRAIN` is set. None: `UNPROVEN: vault`.
- Content folder `C="$R/2nd Brain"`. Page: `$C/Wiki/founder-operating-code.md`. State file:
  `$C/Wiki/founder-operating-code.state.json`. Sketch for grill-me: `$C/Sketches/founder-operating-code.md`.

## Secret scan before every vault write

Memory files sometimes name where a credential lives, and a few have quoted one. **Never copy a
credential value into the page, the state file or the sketch; cite the memory file name instead.**
Before each write, scan the full new text with the same pinned ruleset `journal_event.py` uses,
from a neutral directory, with any `gitleaks:allow` marker neutralised first:

```bash
sed 's/gitleaks:allow/gitleaks-allow/Ig' draft.md | gitleaks stdin --no-banner --redact \
  --exit-code 3 --config ~/.claude/skills/spm/scripts/gitleaks.toml
```

Exit 0: write. Exit 3: a secret-shaped value is in the text; write nothing, remove it, re-scan.
Any other exit, or no `gitleaks` on the machine: `UNPROVEN: secret scan`, write nothing.

## 1. Pre-fill before the first question (read-only)

Draft every section from what the estate already records, so Phill confirms or corrects rather
than starts from blank:

- Memory: `~/.claude/projects/-Users-phillmcgurk/memory/`, feedback-type files first
  (`grep -l 'type: feedback'`), then the founder rulings indexed in `MEMORY.md`.
- `~/.claude/communication-contract.md`: §1–§5 are recorded rules; §7 lists the six questions it
  could not answer. Each §7 question becomes an open item here.
- Existing founder pages: `~/Unite-Group/NORTH-STAR.md`, vault `Wiki/pathway-to-*.md`. Treat
  `~/.claude/NORTH_STAR.md` as a lead only (agent-written, never ratified).

Every pre-filled line cites its source file. Anything inferred rather than quoted is tagged
`[INFERRED]`. Never write a rule in Phill's name that no source records.

## 2. State file

```json
{"updated": "YYYY-MM-DD",
 "sections": {
   "north-star":         {"status": "open", "quotes": [], "sources": []},
   "principles":         {"status": "open", "quotes": [], "sources": []},
   "decision-rules":     {"status": "open", "quotes": [], "sources": []},
   "non-negotiables":    {"status": "open", "quotes": [], "sources": []},
   "how-to-talk-to-me":  {"status": "open", "quotes": [], "sources": []},
   "names-and-aliases":  {"status": "open", "quotes": [], "sources": []}}}
```

`status` moves only `open` → `drafted` (pre-fill or an answer is written) → `confirmed` (Phill's
own explicit yes on that section). Only `status`, `quotes` and `sources` change. A section is never
`confirmed` without a quote from Phill in this session.

## 3. The interview

Run `grill-me` in the main session (never forked: it must talk to Phill). grill-me refuses to
start without a sketch, so first write the pre-fill as a sketch at `$C/Sketches/founder-operating-code.md`
(scanned as above): one heading per section, the draft rules, and a `TBD:` line for every open
question. Invoke grill-me naming that exact file as its sketch. Its rules hold: one question at a time, each with a recommended answer,
dependency-first, and anything the files can answer is looked up, not asked.

- Ask about `open` sections first, then `drafted` ones ("Here is what I have. Keep, change or
  drop?").
- After each answer, write it into the page straight away in Phill's words, add the quote to the
  state file, and move on. Work never waits on the interview.
- Three or more sections waiting on a yes at once: put them on one decision card
  (`references/decision-card.md`) as ticks with my draft as the default.
- Stop when every section is `confirmed`, or Phill stops. Leftover sections stay `drafted` and are
  listed in one line at the end.

## 4. The page

Plain headings, one per section, fifth-grade wording. Each rule: the rule, Phill's quote, the date.
Top line: `Status: <n> of 6 sections confirmed by Phill, <date>`. A page with any unconfirmed
section says so at the top, and /spm treats those sections as `UNVERIFIED`.

When a section is confirmed that answers a `communication-contract.md` §7 question, note it in the
close step's report; ratifying that file stays Phill's own act.
