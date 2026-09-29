---
name: control-design
description: "Use BEFORE writing or changing any check, test, gate, guard or assertion, while the control is being built. Answers one question: will this fire when the defect is present? Catches controls that cannot fail, negative controls that planted nothing, probes answered by a guard before they reach the subject, floors that cannot detect a relocation, and checks that enumerate documents when the surface is what those documents need. Secrets in fixtures belong to credential-custody."
---

# Control Design — will this control fire when the defect is present?

**One question only.** *What surface does it cover, and what claim may I write from it?* is a
different question with a different failure mode — see [`control-scope`](../control-scope/SKILL.md).
Reading a verdict you did not write: [`control-readout`](../control-readout/SKILL.md).
Claiming your own work is done: [`proof-discipline`](../proof-discipline/SKILL.md).
Anything that has to HANDLE a secret: [`credential-custody`](../credential-custody/SKILL.md).

Split from a 480-line file on 2026-08-02, and split again on 2026-08-03 when it had grown
back to 495, and a third time on 2026-08-04 at 232 lines, when the three credential-handling
sections left for [`credential-custody`](../credential-custody/SKILL.md) — they had ridden along
since the first split without ever answering this file's question.

The recurring cause is that soundness and scope read as one topic while writing
and as two topics while debugging. The risk being removed is not length — it is that the half
you needed sat inside a document you opened for the other reason.

**The one line to carry:** *a control that cannot fail is worth exactly as much as no control,
and it costs more, because it also buys false confidence.* Before a control is finished, make
it go red on purpose and watch it.

## Failure-Mode Catalogue (pattern-match fast)

| # | Failure mode | Smell | Detection |
|---|---|---|---|
| 1 | **Sub-scale fixture** | "tiny fixture, all green" | `EXPLAIN (ANALYZE)` at fixture size vs a 50k+ row copy — does the plan node change? |
| 2 | **Forced-plan artifact** | test drops an index / sets `seqscan=off` / stubs a guard to make the path fire | grep the test for `drop index`, `enable_seqscan`, mocks; if the path needs forcing, it is a demo |
| 3 | **Silent cap** | result set "looks complete", never tested past a limit | load `cap+1` matching rows; assert count == `cap+1`, not `cap`. Sweep `max_scan_tuples`, `least(count,N)`, `ef_search` |
| 4 | **Deployed/template drift** | "the migration says X" but the live object differs | `pg_get_functiondef('schema.fn'::regproc)` diff against the `.sql` source |
| 5 | **Observed-not-proven security** | "0 leak" seen once, in geometry where a leak could not show | rebuild fixture with tenants interleaved; run via signed JWT + real role; assert exact id-set |
| 6 | **Vacuous control** | "I broke it and the check caught it" — but the thing you broke was never there | assert the PRECONDITION first (below) |
| 7 | **Misaimed instrument** | "I searched, found nothing, and proved my search works" | a scope failure → [`control-scope`](../control-scope/SKILL.md) |
| 8 | **Answered by the guard** | a real, confident answer from a path that never touched the subject | craft the input to PASS the guard; if the two states now differ, the old probe was measuring the guard |

## 6 in full — verify the precondition before trusting the control

A negative control proves something only if the thing you removed **was present to remove**.
Delete a token that was never there and you planted nothing: the suite passes, and the pass
says nothing about whether the check can fail.

Same class as a suite going green because 19 DB-gated files silently skipped, or a `grep`
whose alternation never matched — **a clean result from a check that never ran looks identical
to a clean result from a clean system.**

It bites hardest on *exemptions*. When you write a rule then exempt yourself from it, the
control proving the exemption is still narrow is the only thing between "declared" and
"disabled". A vacuous control there is worse than none: it manufactures confidence.

```bash
# WRONG — proves nothing if the token was absent
sed -i 's/disabled/_removed/' target.ts && run_suite     # suite passes… of what?

# RIGHT — precondition asserted first, no-op is fatal
grep -q 'disabled' target.ts || { echo "anchor absent — control would be vacuous"; exit 1; }
sed -i 's/disabled/_removed/' target.ts
grep -c '_removed' target.ts        # must be >= 1
run_suite                            # NOW a pass/fail means something
```

**If the anchor is absent, do not silently substitute a different control** — say the control
could not be run, and find one whose precondition holds.

*Earned 2026-08-01: a per-file exemption was reported "controlled" after an attempt to remove a
`disabled` token from a file containing none. Nothing was planted; the 22/22 pass was
meaningless. The real control — planting an **undeclared** construct in the same file — failed
2 tests, which is what the exemption's narrowness actually rests on.*

**This file was itself failure mode 4.** It lived only at `~/.claude/skills/`, which is
gitignored and does not travel, so the lesson about verification proving nothing existed on one
machine and nowhere else. Ruling 2026-08-01: **the repo is canonical, the machine copy is a
deploy artifact, one-way repo → machine, never the reverse.** Editing `~/.claude/skills/` in
place is editing a production server. `skills-drift-check` fails the build if they diverge.

## The first run of a new control is the FAILING one

**A new check is not trusted until it has been observed to FAIL — and to fail for the reason
you think.** Write it, aim it at a defect you have planted, watch it go red, and only then aim
it at the real system. A control whose first observed state is green has been tested for its
ability to agree with you.

**Verify the failure, not just the exit code.** "It failed" is not enough — read the message
and confirm it names the planted defect.

**Controls fail toward green, and the bias is directional, not random.** 2026-08-01/02, four
mis-designs in one session, **all four green**:

| # | Control | What went wrong | Read as |
|---|---|---|---|
| 1 | review tree-integrity | planted file at `*.tmp`, gitignored repo-wide | "no mutation" |
| 2 | secrets-scan coverage | planted secret in `.md`, which is in `_SKIP_EXTS` | "no secrets" |
| 3 | build-freshness | exit code measured through `\| head`, reporting head's 0 | "control passed" |
| 4 | route-exercise | attached to an orphaned server serving the **previous** build | "no broken route" |

Plus a fifth in the tool built to catch exactly this: a history scanner whose input paths all
carried a stray `\r`, so it read **0 blobs** and printed "no secrets found" over 6160 paths.

Five of five landed on green. Not chance — you write a test expecting it to pass, so every
accident lands on the side you expected. **Assume your control is green because it is broken
until you have seen it red.**

**The one that went the other way, and why it does not soften the rule.** A sixth reported FAIL
against a *working* scanner: `scanner | grep -q`, where the scanner exits 1 on a violation, so
under `pipefail` the pipeline was non-zero even though grep matched. A false RED. It cost ten
minutes and was self-correcting, because a red result gets investigated. **A false green is
never investigated, because nobody audits good news.** Both are bugs; only one is dangerous.

Three habits that catch all five:
- **Plant the defect where the check must look**, not merely nearby. Check ignore rules,
  extension filters and path prefixes *first*.
- **Never measure an exit code through a pipe.** `cmd > file; echo $?`, never `cmd | head`.
- **Assert the scan did work**: blobs read > 0, files scanned > 0, paths exercised > 0. A
  checker that examined nothing must fail, not pass.

## A control must REACH the code path that would reveal the defect

Sharper than "the reassuring field cannot fail", and a different fault. Here the control
**ran**, returned a **real** answer, and answered a **different question** — because the
subject sits behind a guard that replies first.

*2026-08-04, DR-NRPG.* A watcher decided `webhook_secret_configured` from "HTTP 400 mentioning
signature". The handler validates the signature *header* before it reads
`STRIPE_WEBHOOK_SECRET`, so an unsigned request is answered by the guard, not by the thing
being measured — and gets that 400 whether the secret exists or not. The field read `true` for
every run the watcher had ever made. It was false.

**The discriminating fixture is a PAIR, and it belongs on the live endpoint, not in a file:**

    unsigned            ->  400 "Missing Stripe signature"        <- the guard talking
    signed-but-invalid  ->  500 "Missing STRIPE_WEBHOOK_SECRET"   <- the subject talking

Same endpoint, same second, opposite verdicts. Craft the input so it **passes the guard and
fails at the subject**. If both states still produce the same response, the probe cannot see
the subject and owes you *undetermined* — not a verdict.

**Ask of any probe: what is the first thing that could answer this, and is it the thing I am
asking about?** Ordering decides who replies — header before secret, auth before handler,
validation before write — and the earliest replier wins.

## A page is not a surface — what it NEEDS is classified separately

**A control that enumerates documents has not enumerated the surface.** Walk the route tree and
you have found pages and endpoints. What each one needs in order to *work* — its bundle, its
styles, its data calls — is classified by a different rule, usually a path prefix. A change to
paths moves those across a security boundary without touching the document, and the control
stays green because everything it asserts about the document is still true.

**It presents as broken, not blocked**, which is what makes it expensive. A blocked page sends
you to the auth config. A page that renders unstyled, whose bundle 302s, sends you to the CDN,
the build, the deploy — the investigation starts in the wrong system entirely.

*2026-08-04, Pi-Dev-Ops.* Setting `assetPrefix` for a multi-zone move put every `/_next/*` URL
inside `/command-centre`, a protected prefix. The **public** login page's own CSS and JS were
then answered with a redirect to login. Twenty-two auth assertions stayed green; not one probed
an asset path.

**Ask of any path-prefix rule: what else did that prefix just capture?** Probe one of those, and
probe a near-miss — `/_nextdoor`, or `?ref=/_next/x` — so the boundary is asserted, not assumed.
