---
name: ci-quality-parity
description: Run every gate CI's "Quality Checks" job runs, LOCALLY, before you push or open a PR — so a locally-green branch never opens UNSTABLE. Use before any git push / gh pr create in RestoreAssist, and whenever a PR shows mergeStateStatus UNSTABLE with a red Quality Checks. Triggers on "quality checks failed", "PR is unstable", "emoji guard", "lucide guard", "au-english", "check:no-emoji", "green locally red in CI".
---

# CI Quality-Parity

> **Superseded for enforcement, 19/09/2026.** `pr-release-gate/scripts/ci_mirror.py` now runs
> every step of every pull_request workflow (this repo's Quality Checks included, with its
> Postgres service in Docker) and `pr_release_gate.py issue` refuses to sign a receipt without
> it. This page stays as the explanation of the introduced-vs-pre-existing distinction below;
> you no longer need to remember to invoke it.

The RestoreAssist release-gate recorder runs type-check, lint, tests and build. **CI's "Quality
Checks" job runs ~10 MORE guards on top of those.** None of them are in the local gate, so a
branch can pass the full release gate, get a receipt, push — and open UNSTABLE the moment one of
those extra guards fires. That is not hypothetical: PR #1998 (2026-08-08) passed the local gate,
got `PR_RELEASE_GATE_PASS`, and opened UNSTABLE because two of its own new docs contained `⚠️`/`✅`
that exceeded the emoji baseline.

This skill closes that gap: run the **same** guard set locally, first, and only push a branch that
is green on all of it.

## The gap, precisely

The release-gate recorder's `--test` commands are a SUBSET of CI. The guards it misses (all fast,
all no-DB) are, from `.github/workflows/pr-checks.yml` → job `quality-checks`:

| CI step | command | catches |
|---|---|---|
| Emoji guard | `pnpm check:no-emoji` | emojis over the baseline (docs, comments, copy) |
| Lucide guard | `pnpm check:no-lucide` | raw lucide imports instead of `RAIcon` |
| Spec-docs layout guard | `pnpm check:spec-docs` | spec/doc files in the wrong location |
| Encoding guard | `pnpm check:encoding` | non-UTF-8 / bad byte sequences |
| Data-source SSOT gate | `pnpm check:ssot` | data read from a non-SSOT source |
| Standards citation gate | `pnpm check:standards` | IICRC/AS citations missing edition+section |
| Verbatim standards tripwire | `pnpm check:no-verbatim` | verbatim standard text (copyright) |
| Marketing zero-verbatim gate | `pnpm check:marketing-verbatim` | verbatim marketing/source text |
| Australian-English guard | `pnpm check:au-english` | US spelling in content |
| AI guardrail audit | `pnpm audit:ai` | ungated AI calls / prompt-safety |
| API route audit | `pnpm audit:api` | routes missing auth/validation |

type-check, lint, `vitest run --config config/vitest.config.js` and `pnpm build` are already in the
release gate — do not re-run them here unless you skipped the gate.

## Run it — enumerate from CI, never from this list

**Do not trust the table above as the source of truth** — steps get added to CI and this file
drifts. Derive the live set from the workflow each time:

```bash
# the guard/audit commands CI actually runs in the Quality Checks job, in order
grep -oE 'pnpm (check:[a-z-]+|audit:[a-z-]+)' .github/workflows/pr-checks.yml | sort -u
```

Then run each. **Use `while read`, never `for c in $(...)`** — the commands are two words
(`pnpm check:no-emoji`) and a `for` loop word-splits them into `pnpm` + `check:no-emoji`, which
silently runs `pnpm` (help text) then a not-found command. That bug will make every guard look
"failed" for the wrong reason:

```bash
grep -oE 'pnpm (check:[a-z-]+|audit:[a-z-]+)' .github/workflows/pr-checks.yml | sort -u |
while IFS= read -r c; do
  printf '== %s == ' "$c"
  if eval "$c" >/tmp/pq.log 2>&1; then echo PASS; else echo FAIL; tail -6 /tmp/pq.log | sed 's/^/    /'; fi
done
```

## Introduced vs pre-existing — the distinction that makes this usable

**Main itself carries guard debt.** On 2026-08-08 a clean `origin/main` failed `check:no-lucide`
(8 files) and `audit:api` (2 public routes) — pre-existing, nothing to do with the branch under
review. If the skill demanded "all guards green", no branch could ever pass, because CI runs these
with `bash -e` and stops at the FIRST red guard regardless of who caused it.

So the rule is not "all green". It is: **no guard may be redder because of your diff.**

For each FAILING guard, decide which case it is:

- **Introduced** — the guard names a file your branch changed, or a baseline-counted guard (emoji,
  lucide, verbatim) reports MORE violations than the same guard on `origin/main`. This is yours.
  Fix it before pushing.
- **Pre-existing** — the guard only names files your branch did not touch, and the violation count
  is unchanged from `origin/main`. Not yours. Do NOT fix it in this PR (that is scope creep across
  unrelated files) and do NOT bump its baseline to paper over it. Record it as known main-wide debt
  and move on; it blocks every PR equally and is cleared by its own dedicated PR.

Cheap way to tell them apart for a baseline-counted guard: run it on your branch, note the count;
`git stash` / check out `origin/main`, run it again, compare. Same count = pre-existing. Higher on
your branch = introduced. For a file-naming guard, intersect the named files with
`git diff --name-only origin/main...HEAD`.

A push is parity-clean when every guard that your diff made redder is green again — not when the
whole repo is green.

## Where this sits in the release flow

It is a **pre-gate step**, not a replacement for `pr-release-gate`:

1. `ci-quality-parity` (this) — the extra CI guards are green locally.
2. `pr-release-gate` — test the exact commit, independent review, receipt.
3. Push + draft PR.

Running this FIRST means the review and receipt bind to a commit that will also survive CI, instead
of discovering a guard failure after the PR is open and having to add a commit (new HEAD →
invalidated receipt → a second full review). One emoji costs a whole re-gate if caught late.

## When a guard legitimately needs a baseline bump

Some guards (emoji, verbatim) carry a baseline of historical violations. The guard's own message
says whether `--update-baseline` is allowed. **Default to removing the emoji / fixing the content,
not bumping the baseline** — the baseline is for the pre-existing backlog, not new additions. Bump
it only for the historical-backlog case the guard names explicitly, and say so in the commit.

## Fastest fixes for the common ones

- **Emoji**: replace with a text token. `⚠️`→`WARNING:`/`[!]`, `✅`→`DONE`/`[x]`, `🚨`→`ALERT:`.
  For branded UI use `[ra:name]` per `prompts/no-generic-emojis.md`.
- **Lucide**: import `RAIcon` from the brand icon registry, not `lucide-react` directly.
- **au-english**: `-ize`→`-ise`, `color`→`colour`, `analyze`→`analyse`, etc.

## What breaks without this

The estate auto-readies draft PRs and squash-merges on green within minutes (see `merge-gate`). A
guard failure holds the PR UNSTABLE, so it will not auto-merge — good — but it also means every
locally-gated push that skipped these guards becomes a manual round-trip: diagnose the CI log, fix,
re-commit, re-review, re-receipt, re-push. Running the guards up front turns that loop into one
clean push.
