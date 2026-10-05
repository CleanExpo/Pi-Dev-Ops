# Licence classes + the fail-closed rights gate

The rights gate runs BEFORE curation and BEFORE any board. It is fail-closed: anything not
positively classified into a reproducible/reference class is `unknown-rights-quarantine` and never
reaches a board. Robots/terms are checked before extraction, not after.

## The five classes (`licenceClass`)
- **`publicly-reproducible`** — explicit open licence verifiable at an evidence URL: public
  domain / CC0, CC-BY / CC-BY-SA (attribution captured), government open-licence, or an owner's
  explicit reuse grant. The only class safe to store the pixels of.
- **`nominative-reference-only`** — copyrighted but lawfully viewable; used ONLY as a described
  reference to design an original. Store the record + description + style tokens, NOT the pixels
  for republication.
- **`licensed-internal`** — covered by a licence the estate already holds (e.g. an Artlist
  subscription). Usable within that licence's terms; record the licence source.
- **`protected-do-not-republish`** — known rights-reserved / no reuse grant. Reference-describe
  only; never boarded as a redistributable asset; flagged for human review if legally
  consequential.
- **`unknown-rights-quarantine`** — rights could not be established. Goes to `quarantine/`. Never
  guessed permissive, never boarded.

## Every record carries the evidence
- `licenceEvidenceUrl` — the page/API field that proves the class (a licence tag, a terms page, a
  Commons licence template). No evidence URL ⇒ the class is `unknown-rights-quarantine`.
- `robotsVerdict` — `allow` | `disallow` | `unknown` from the source host's robots.txt/terms,
  checked before extraction. `disallow` ⇒ skip + log; never extract.

## Gate rules (apply in order, fail-closed)
1. robots/terms `disallow` → skip the page entirely, log the skip.
2. No verifiable licence evidence → `unknown-rights-quarantine`.
3. Ambiguous between two classes → take the MORE restrictive one (never the permissive guess).
4. `protected-do-not-republish` and `unknown-rights-quarantine` → excluded from every board; only
   `publicly-reproducible`, `nominative-reference-only`, and `licensed-internal` may appear, and
   the last two only as described references + style tokens.

Completion criterion: every record has a `licenceClass`, a `robotsVerdict`, and — for any board
candidate — a non-`unknown` class with a populated `licenceEvidenceUrl`.
