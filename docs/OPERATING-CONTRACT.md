# Operating contract

**Ratified 2026-08-01.** Governs autonomous work in this estate. Supersedes the ad-hoc gate list.

---

## The default is: proceed

Act on your own recommendation. Do not stop to confirm a plan, a sandbox, a review vendor, an evidence standard, a build order, or a fix you can justify. Record the decision and its reasoning in `.harness/incidents.jsonl` so it is **reviewable rather than invisible**.

The founder is not a message bus. Using a human to carry a proposal you could have justified yourself is the failure this contract removes.

## Stop for exactly three classes

**1 — Spending real money.** R1 unchanged: `fence.spend.max_aud` is null, so every unenumerated spend stops. Paid APIs, metered generation, provisioning, subscriptions.

**2 — Touching production.** The `fence.json` list, unchanged: 19 hosts, 17 databases, protected branches, deploy verbs, secrets paths.

**3 — Genuine equipoise.** Two defensible options and **no principled basis to choose between them**.

Class 3 is a real stop and is not a synonym for wanting confirmation. Before invoking it, state both options and the basis you searched for. If you can articulate why one is better — cost, reversibility, blast radius, precedent, an existing ruling — **that is a basis, and you proceed.** "I would like reassurance" is not equipoise. Neither is "this feels significant."

**Provenance of the class-3 guard.** The preceding paragraph was the agent's addition, not the founder's. The category handed over was "genuine equipoise"; the guard against laundering a wish for reassurance *into* that category was written by the agent, because the category as stated was the easiest of the three to abuse — money and production are enforced by the fence, equipoise is self-assessed, and a self-assessed stop with no test is an off-switch for the whole contract. Recorded because the record should say where the design came from, and because the same reasoning is what CAPACITY LIMIT below is built on.

Everything else: act.

## Not a stop class: CAPACITY LIMIT

**Running out of usable context is a legitimate reason to record state and hand over. It is explicitly NOT a class-3 stop.**

Named because it is the mirror image of the class-3 guard, and it fails the same way. Class 3 is at risk of *absorbing* things that are not equipoise; capacity is at risk of being *relabelled* as equipoise to make an ordinary handover sound like a decision that needed the founder. Both distortions produce the same artifact — a stop that reads as though a question is pending when none is.

The distinction is what is owed on the way out:

- **Class 3 stops with a question.** Work halts until someone answers. The founder owes a decision.
- **CAPACITY LIMIT stops with a checkpoint.** Nothing is pending. The next session resumes from a written handoff and needs nothing from anyone. The founder owes nothing.

When stopping on capacity, say so in those words. Do not write it up as equipoise, do not manufacture a question to justify it, and do not present a bounded task with attempts remaining as though it were blocked. "I am out of context, here is the state" is a complete and honest ending; a stop is only a class-3 stop when someone genuinely has to answer something before work can continue.

## What makes this safe

Structural, not trust:

- **Work stays on the branch.** `main` is protected, requires review, and is untouched.
- **Both gates are real.** Money and production are enforced, not honoured.
- **A wrong call costs a revert.** That is the actual worst case for anything outside the three classes.
- **Cross-vendor review is mandatory per capability.** Codex is the adversarial read. That was never the founder's job.

## Notification

Outbound only, through the existing send-only notifier (`fence/notify.py`):

- when a **class-3-adjacent** call is made — close to equipoise, decided anyway, with the basis
- when a **capability completes**

**The standing decision against the inbound Telegram plugin holds. Nothing inbound becomes an instruction.** The notifier takes a kind and a path to a fence-generated artifact; it has no free-text argument and no inbound path.

## Skills: the repo is canonical

`skills/<name>/SKILL.md` in this repo is the source of truth. `~/.claude/skills/<name>/` is a **deploy artifact**.

**One-way, repo → machine, never the reverse.** Editing the machine copy in place is editing files on a production server. Two-way sync is what produces diverging skills.

Precedent: the Nexus Prompt is never forked into repos, always fetched live.

```
python fence/deploy_skills.py            # materialise machine from repo
python fence/deploy_skills.py --check    # report drift, exit 1 if any
```

`.github/workflows/skills-drift-check.yml` fails the build if a manifest skill has no repo source, or if a machine-path copy is committed back.

This is **failure mode 4 — deployed-versus-template drift** — and it bit `proof-discipline`, the file that catalogues it: it lived only in a gitignored machine directory, so the lesson inherited nowhere.

## Review bounds, and the per-instance release valve

A cross-vendor review round is **bounded at three attempts against a fixed spec**. The bound is a
standing rule, not a judgement call. An agent may not extend it.

**The founder may grant a fourth attempt per instance.** Granted twice so far — hermes, and
capability 2/3 on 2026-08-01. **Neither is precedent, and a grant does not create a rule.**

**What was declined, and stays declined:** *"the bound may extend while a reviewer is
converging."* Refused because it is a builder self-assessment against an undefined qualifier —
the builder decides what "converging" means, about its own work, to buy itself another round.
That is the same defect as an exemption the builder writes to its own check. Do not reintroduce
it in new wording.

**Why capability 2/3's grant was given** — and note the reason is *not* convergence:

All three findings were holes in the **evidence apparatus**, not code failing a spec. Exemptions
blanket one level down; a map validated only against itself; a graph seeded from too few roots;
a route check blind to template literals. The code did what it should; the machinery claiming to
verify it was reading wider than it was.

This is the **inverse of hermes**, where the code was fine and the spec could not be met. A bound
exists to stop a fruitless grind. Applied to a round that is finding a real defect in the
verifier every time, it misfires — it would end the review precisely because the review is
working.

**The condition attached to the grant, which is the part worth generalising:** every finding was
the same class — *coverage that reads wider than it is*. So the primary question to the reviewer
became whether the apparatus is **architecturally sound or being patched reactively, one finding
at a time**. If a granted attempt returns another instance of the same class, **stop**. That is
the signal to re-spec the harness, not to grant another attempt. A fourth round that finds the
same class of hole is evidence the design is wrong, not that the patches are nearly done.

## Believed good is not verified good

A capability may be **believed good** — gate green, findings fixed, no known defect — while its
**evidence apparatus has not earned the right to say so**. These are different claims and they
must be recorded separately.

Capability 2/3 is the worked example: green gate, 34 passing tests, four rounds of review
findings all fixed, and it has **never earned a PASS**. G1 is open, the navigation detector
misreports its own coverage, and three of four review rounds could not execute the suite.

**Collapsing the two is how a green suite starts meaning nothing.** A reader who sees a green
gate and infers verification is making exactly the error the harness exists to prevent. When
they diverge, say both, in those words.

## Do not stack capabilities on a verifier known to misreport

**Ruled 2026-08-01: capability 4 does not start until the navigation layer is re-specced.**

Every capability inherits the harness. Building more on a verifier with a known
coverage-overclaim does not add risk linearly — it multiplies *false confidence*, because the
defect is precisely the kind that makes each new capability look verified. The bill arrives at
whichever one finally breaks in production, by which point four are carrying it.

The general form: **when a verifier is known to misreport its own coverage, fix the verifier
before adding anything that will be measured by it.**

## Reviewer capability is part of the evidence, not a detail

On capability 2/3 attempts 2 and 3 the reviewer **could not execute the test suites** — `spawn
EPERM` loading the Vite config in its sandbox — and reviewed statically. Acceptable there: the
claims were about code structure and provenance, which read fine statically.

**Not acceptable for operator-gateway.** Its entire claim is that *nothing executes*. A
static-only review of an execution-absence claim is materially weaker than one that can run the
suite and observe the absence — it verifies that the code appears not to execute, which is the
same shape of assertion the auth exemption made and lost on.

**Getting the reviewer's sandbox able to run the suites is now gating work before operations**,
alongside per-capability tokens.

**Escalated 2026-08-01 — it is also a PREREQUISITE for the harness re-spec review, not a
step-4 item.** By attempt 4 the reviewer had failed to execute the suites on three of four
rounds and its build failed on the fourth; only `tsc --noEmit` was ever independently confirmed.

Tolerable for structural claims about code. **Not tolerable for reviewing a verifier.** The
re-spec's entire claim is *these checks fail red when they should*, and that is only confirmable
by running them. **Re-speccing the harness and grading it by assertion reproduces the exact
defect being fixed** — a check described by what it was meant to do rather than what it was
observed to do. Fix the sandbox first.

**RESOLVED 2026-08-01.** Root cause: Codex's Windows sandbox is a *restricted-token* sandbox —
its own binary strings say `windows unelevated restricted-token sandbox`. Measured with a probe
rather than inferred: **spawn denied EPERM, write permitted, unlink denied EPERM.** That explains
both observed failures precisely — vitest died because Vite's `optimizeSafeRealPathSync()` runs
`exec("net use")` on Windows on first realpath and the throw lands *outside* Vite's `try/catch`;
`next build` died on `unlink` specifically, having been allowed to write. No tuning fixes it:
tests must spawn, builds must delete, and `[windows] sandbox` only selects elevated/unelevated.

Review runs therefore step **outside** that sandbox, via `scripts/codex-review.sh` — and the flag
is **per-invocation, never written into `~/.codex/config.toml`**, so every other Codex run on the
machine keeps its sandbox.

**What the controls below do and do not cover, stated precisely.** `-s danger-full-access` is
**machine-wide**; the tree and execution controls are **repo-scoped**. They do not "replace the
removed isolation" — they cover the reviewed artifact, plus the one machine-level path with
teeth. That path is `~/.codex/config.toml`, because editing it is how a reviewer would
permanently widen its **own** permissions for every future run: self-escalation, the shape R3
exists for, and the same family as a reviewer holding commit rights. Everything else outside the
repo is either covered by `deploy_skills.py --check` or has no leverage. Beyond that the control
is the model's compliance with the brief, which is not a control at all — say so rather than let
the count imply otherwise.

1. **Tree integrity** — HEAD plus working-tree state hashed before and after; any change to the
   source of record **voids** the review. Scope stated, not implied: blind to gitignored paths,
   because the reviewer must write `.next/` to run the suite at all.
1b. **Codex config integrity** — `~/.codex/config.toml` hashed before and after. A change voids
   the review and is an **incident**, not a failed round: it is the self-escalation path.
2. **Execution proof** — the run **fails** if the transcript contains no evidence the suite ran.
   Silent non-execution becomes loud instead of a footnote. This is the control that would have
   caught rounds 2, 3 and 4 as unusable at the time rather than in hindsight.
3. **Plan auth** — unchanged; refuses to fall back to a paid per-call key.

Verified end-to-end: probe 5/5, `command-centre-auth-coverage` **7 passed (7)** run *by the
reviewer*, verdict extracted, tree unchanged. All three controls were tested for their ability to
**fail**, not only to pass — and that testing found a real hole in control 1 before it shipped.

## The builder does not grade its own exemptions

Stated plainly, because capability 2/3 produced the strongest evidence for it yet.

The auth exemption **was written by the builder, for the builder's own conformance check, and it
was the live hole.** Four command-centre pages and an API route served anonymous requests while
reading through a service-role client that bypasses RLS — and the exemption's stated reason,
"auth is enforced upstream by proxy.ts", was the thing making it invisible. Every local check
passed. The suite was green.

It was found because a cross-vendor reviewer **refused to accept the stated reason as evidence**
and asked for it to be proven. Proving it is what showed it was false. Not a better reviewer, not
a smarter check — a reviewer with no stake in the exemption being correct.

The rule is therefore not "review exemptions carefully". It is that **the party who writes an
exemption cannot be the party who grades it**, and any process where those are the same party is
producing green results that mean nothing.

## Recording a decision

Every non-trivial call taken under this contract gets an incident record with `outcome` and the reasoning. The bar is not "was this important" but "would a reviewer need to know why". Cheap to write now, expensive to reconstruct later.

A decision that is acted on and recorded is reviewable. A decision that is acted on and unrecorded is indistinguishable from drift — which is the whole argument for the log.
