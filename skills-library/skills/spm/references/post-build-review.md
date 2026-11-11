# Post-build review: up to three readers on the built diff

The engineering bench (workflow step 9) reviews the SPEC, before any code exists. Nothing reviewed
the BUILT diff before the release gate. This step does, cheaply, while the builder still holds the
context to fix what it finds.

**This is a pre-check. It does NOT replace the pr-release-gate independent review.** All the
readers are Claude, the builder's own family. The release law still needs a non-builder lane
(`independent_review.py`, lane order from `lane_registry.py --list`) bound to the exact final
commit. A clean pre-check is never review evidence and never goes in a receipt.

## When, and how many readers

Three readers cost three agent runs, so the seat count follows the diff. Measure the diff first,
excluding lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`,
`Cargo.lock`), generated files, and vendored paths (`scripts/vendored-skills.txt` here; `vendor/`,
`node_modules/`, `dist/`, `build/` elsewhere). Those paths are also left out of every reader's diff.

| Diff after exclusions | Readers |
|---|---|
| docs only | none; say so in one line |
| T0, or a Micro-spec under about 20 changed lines | `crew-reviewer` only |
| anything else | `crew-reviewer` + `crew-security`, plus `eng-performance` only when the diff touches its own triggers: queries, loops over collections, pagination, or a request path |
| over about 3,000 lines | the same readers, one dispatch per group of files so each brief stays readable |

Run after the build passes its own Done criteria locally, before the release gate.

## Dispatch: one message, the selected agents in parallel

Freeze the head first: note `base` and `head` SHAs and do not commit while the readers run.
Send every selected `Agent` call in ONE message. Each is read-only (their definitions allow only
Read, Grep, Glob, Bash and WebFetch) and gets the same brief:

| Agent | Question | Looks at |
|---|---|---|
| `crew-reviewer` | Does it work? | behaviour against the spec's §15 criteria, edge cases, error paths, tests that cannot fail |
| `crew-security` | Is it safe? | secrets, auth, input handling, permissions, dependencies, fail-closed behaviour |
| `eng-performance` | Is it fast? | queries, loops over collections, request paths, payload size, anything that grows with data |

Brief (fill the brackets, keep the rest):

```text
Read-only review of [repo] at head [head SHA], base [base SHA]. The diff is
`git diff [base]..[head] -- [paths, excluded paths left out]`. The spec is [path to spec.md]. Your question: [question from the table].
Do not edit, commit or push anything. Return ONLY this JSON:
{"head": "[head SHA]", "findings": [{"severity": "high|medium|low", "file": "path",
 "line": 0, "failure": "what goes wrong, for whom, when", "proof": "one shell command that,
 run from the repo root, shows the failure (non-zero exit, or output that names it)"}]}
An empty findings list is a valid answer. No finding without a proof command.
```

## The main thread decides, not the readers

1. A report whose `head` is not the frozen head is discarded.
2. Re-run every `high` finding's `proof` command yourself on the frozen head. It counts only if
   it shows the failure. A proof that cannot show the failure (passes, errors on setup, or needs a
   secret) is downgraded to `low` and noted, never silently dropped.
3. A confirmed `high` blocks the release gate: fix it, re-run the Done criteria, and re-run only
   the reader that raised it on the new head.
4. `medium` and `low` go into the release-gate brief as known items, so the independent lane sees
   them; fix them when cheap.
5. Record one line in the spec's §14: `Post-build review: <n> high confirmed, <n> fixed, head <sha>`.

A reader that never returns, or returns no parseable JSON, is `UNPROVEN: post-build <agent>`, not
clean. Re-dispatch it once; if it fails again, say so in the release brief and carry on.
