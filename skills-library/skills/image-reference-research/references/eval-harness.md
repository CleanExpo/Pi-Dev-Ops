# Evaluation harness + acceptance bar

The skill ships with an offline, zero-network eval so the machine-checkable core is provable in CI.
Run it from the skill root:

```
node scripts/eval.mjs        # exit 0 = pass, 1 = fail
```

## What it asserts
- **Dedup F1 ≥ 0.9** — perceptual dedup (dHash + Hamming ≤ 8) collapses near-duplicate groups and
  keeps structurally-distinct images apart. Scored as pairwise same-cluster F1 against the labelled
  fixture groups in `eval/seed/fixtures.mjs`.
- **Licence-class accuracy ≥ 0.95** — `rights.mjs classifyLicenceTag` maps a known licence tag to
  the correct class (fail-closed to `unknown-rights-quarantine`), scored against labelled tags.
- **Board invariant (hard 0)** — `board.mjs renderBoard` includes only board-eligible records; a
  `protected-do-not-republish`, `unknown-rights-quarantine`, or `quarantined:true` record never
  reaches the board HTML. This is a zero-tolerance check, not a threshold.

Current status on the shipped fixtures: dedup F1 = 1.000, licence accuracy = 1.000, board
invariant clean.

## The seed set
`eval/seed/fixtures.mjs` holds **deterministic, procedurally-generated grayscale matrices** — no
downloaded images, no network — forming labelled duplicate groups (brightness/blur variants that
must collapse), hard negatives (structurally distinct patterns that must not), and licence-tag
cases. This is the CI-safe core.

**Phase-1 enrichment (documented, not yet built):** replace/extend the synthetic set with ~50
labelled images from licence-native sources (Openverse / Wikimedia Commons) — the only legally
zero-risk corpus — with hand-labelled near-duplicate pairs and licence classes. The metrics and
thresholds are unchanged; only the corpus grows. Until then the synthetic core guards regressions.

## Acceptance (skill is "done" per the design)
Every board image has a complete provenance record and a non-`unknown` licence class; dedup F1 ≥
0.9 and licence accuracy ≥ 0.95 on the seed; facet coverage reported with named gaps; 0 protected
images in any output; Exa/Apify/Firecrawl lanes each degrade honestly and lane-stamped; the skill
passes the `skill-authoring-standard` review checklist and `SKILL.md` is ≤ 200 lines.
