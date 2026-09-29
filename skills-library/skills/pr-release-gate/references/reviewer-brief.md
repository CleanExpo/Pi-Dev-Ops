# Reviewer brief template

The brief carries ONLY what varies per review. Everything stable lives here and in
[`reviewer-report-schema.md`](reviewer-report-schema.md) — reference them, never restate.
Seven hand-drifted briefs in one night (95→29 lines) cost two rounds to schema mismatch;
this template is the interface that prevents that.

## Template — fill the {slots}, delete nothing else

```
INDEPENDENT REVIEWER, PR release gate. REFUTE, do not bless. Default FAIL when uncertain.

Repo: {org/repo}. Your cwd is a disposable review worktree at the candidate head.
base_sha: {40-char base}
head_sha: {40-char head}
implementation_agent: {claude|codex — the --primary-agent `issue` will be run with}
Scope: {full review | drain-verification of findings <ids> | rebind after rebase/merge}
Budget: ~{N} tool calls.

REPORT CONTRACT — non-negotiable field names:
Write `reviewer-report.json` in your cwd EARLY, then revise. Schema and exact field
names: ~/.claude/skills/pr-release-gate/references/reviewer-report-schema.md
(schema 2; verdict PASS|FAIL; `blocking_findings` = P0/P1 only; P2s are documented
warnings with a ticket reference; `checklist` and `coverage` as below). A report in any
other shape is rejected by the recorder unread. Set `implementation_agent` to exactly the
value above, even when the PR's author is a bot such as dependabot: it names the agent
releasing the change, and `issue` rejects any other value.

WHAT PASS MEANS — it is a checklist, not an absence of objections. You may return PASS
only when BOTH hold: every item below is answered PASS or N/A with the evidence that
discharged it, AND there are zero unresolved P0/P1 findings. An item you did not do is
not a PASS; say N/A with a reason, or return FAIL. Emit all eight, by these exact ids:

  coverage-ledger          Every file in the two-dot diff appears in `coverage`, each
                           not-reviewed entry carrying a reason. The gate computes the
                           changed set itself and rejects a ledger that omits a file.
  plan-conformance         The diff implements what was approved, not something adjacent.
  weakened-checks          Searched for removed assertions, added skips, silenced linters,
                           tests asserting nothing, swallowed errors. NAME THE SEARCH.
  mutation-control         Every test claiming to prevent X DEMONSTRATED failing under a
                           mutant reintroducing X, source restored byte-identical. A
                           regression test that cannot fail is P0.
  guard-falsification      For each guard or allow-list, the bad input PLANTED AND RUN.
                           Reading the regex does not discharge this.
  clean-environment-suite  Suites run ONCE, exactly as CI invokes them, via
                           `env -i HOME="$HOME" PATH="$PATH" TERM=dumb ...`. Never export
                           env vars first — poisoned evidence voids the run. Record counts.
  blast-radius             Direct callers of every changed function or contract examined.
  outbound-actions         Nothing in the diff creates an account, sends a message,
                           publishes, purchases, or pushes.

COVERAGE — `coverage.reviewed` plus `coverage.not_reviewed` must account for every file in
the two-dot diff, and for nothing outside it. If the diff is larger than your budget, that
is a real answer: list what you did not read, with the reason. An under-covered review that
SAYS SO is usable; one that reports clean over a fraction of the surface is not.

RUBRIC — every review, regardless of scope:
- Cite file:line and demonstrate; do not theorise. Findings must be in the changed code
  or its direct blast radius.

KNOWN FACTS (verified this session — do not re-derive):
{facts: pre-existing failures with proof location, suite counts at this head, scope rulings}

{scope-specific attack list, if any}
```

## Rules for the dispatching agent

- Pipe the brief via stdin with a trailing `-` (`codex exec --sandbox workspace-write - < brief`);
  a positional prompt hangs in background runs.
- One brief per SHA. A new commit means a new brief with the new head — never ask a
  reviewer to "re-emit" a verdict for content it has not re-anchored to a SHA.
- Never author or edit the reviewer's report file yourself, including reformatting it.
  If the recorder rejects the report's shape, send the reviewer the recorder's exact
  error text and this template's REPORT CONTRACT block; the reviewer re-emits or refuses.
