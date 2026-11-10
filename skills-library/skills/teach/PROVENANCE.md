# Provenance

- Upstream: https://github.com/mattpocock/skills/tree/ad5400b930b297b0c0cb231ff1ffe42a7da666aa/skills/productivity/teach
- Pinned commit: `ad5400b930b297b0c0cb231ff1ffe42a7da666aa` (7 Oct 2026, "teach: anchor workspace paths, vary quiz answer position (#1183)")
- Upstream docs read: `docs/productivity/teach.md` at the same commit (its FAQ is the source of the failure modes below).
- Licence: MIT, copied unchanged to `LICENSE`.
- Reviewed: 18 Oct 2026, every file in the upstream folder read in full.

## Vendored unchanged

`references/{mission,learning-record,glossary,resources}-format.md` are the upstream
`*-FORMAT.md` files, renamed to the library's lowercase convention. One edit: the link to
`SKILL.md` in `resources-format.md` now points to `../SKILL.md`, because the file moved into
`references/`.

## Changed from upstream, and why

| Change | Upstream evidence |
|---|---|
| `effort: high` in frontmatter | Docs: higher effort gives clearly better lessons than medium |
| Starting-point diagnostic before lesson one | Issue #725; docs: "most common real complaint" is assumed knowledge and undefined jargon |
| `assets/quiz.js` shuffles answers at render time | Issue #335: instruction-only fix left the answer in slot A 33 of 33 times; docs say the real fix is a component |
| `GLOSSARY.md` linked from the workspace table | Issue #559: the format shipped but `SKILL.md` stopped linking it |
| `REVIEW.md` spaced-review queue, review before new material, explicit stop signal | Docs: no spaced repetition and no exit criteria |
| Lesson prose gated by `unslop`; "check this lesson" block | Estate writing standard; the discernment pattern from Anthropic's `discernment-nudge` (check facts, question reasoning, notice missing context) |
| `/output-style Learning` for coding drills; forked source reading | Claude Code built-in Learning style (`TODO(human)`), skill `context: fork` |
| Project overlays (CARSI IICRC and Australian-production rules) | CARSI `CLAUDE.md` |
| Section order follows the library house manner | `skill-authoring-standard/references/pocock-manner.md` |

## Re-deriving

To take a newer upstream: read the diff from the pinned commit to the new one for
`skills/productivity/teach`, re-apply the table above, update the pin here and in
`scripts/test_teach.mjs`.
