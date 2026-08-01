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

Everything else: act.

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

## Recording a decision

Every non-trivial call taken under this contract gets an incident record with `outcome` and the reasoning. The bar is not "was this important" but "would a reviewer need to know why". Cheap to write now, expensive to reconstruct later.

A decision that is acted on and recorded is reviewable. A decision that is acted on and unrecorded is indistinguishable from drift — which is the whole argument for the log.
