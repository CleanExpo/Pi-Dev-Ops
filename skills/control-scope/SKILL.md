---
name: control-scope
description: Use when a check has RUN and you are about to say what it proved, or when choosing where to plant a canary, narrow a search, or enumerate the surface a guard covers. Answers ONE question, what did the instrument actually look at and what sentence am I permitted to write. Catches searches aimed at the wrong name, checks that enumerate a fixed set and go stale, canaries planted where the instrument was already known to reach, and claims upgraded from "within targeted scope" to "by discovery". Triggers on "confirmed", "nothing found", "scanned clean", "no matches", "I searched for", "-maxdepth", "--include", "sampled", "the broad search timed out", "we use discovery now".
---

# Control Scope — what did it look at, and what may I claim?

**One question only.** *Will this control fire when the defect is present?* is a different
question — see [`control-design`](../control-design/SKILL.md). Reading a verdict you did not
write: [`control-readout`](../control-readout/SKILL.md). Claiming your own work is done:
[`proof-discipline`](../proof-discipline/SKILL.md).

**The one line to carry:** *a right conclusion from a blind instrument reports identically to
rigour.* Absence of evidence is evidence of absence only for the surface the instrument actually
traversed.

**Incidents in full** — the four cases each rule was earned from are in
[`references/worked-examples.md`](references/worked-examples.md); open it when you need the
narrative rather than the rule.

## Failure mode 7 — a positive control validates the INSTRUMENT, not the AIM

A positive control proves your search *mechanism* works. It says nothing about whether you
pointed it at the right target. Both failures emit identical output — an empty result from a
correctly-functioning search — and only one means "absent".

`control-design`'s mode 6 is *the control could not have failed*. Mode 7 is *the control worked
perfectly and was aimed at the wrong thing*. Running 6 does not protect you from 7.

*In one line:* I searched for `middleware.ts`, found none, ran a positive control that passed,
and reported ~13 unauthenticated routes with exploit chains. Next.js 16 had renamed the file to
`proxy.ts`; it gated seven prefixes and every finding collapsed. **The passing positive control
is what made the wrong conclusion feel earned.** A live `curl` returning 401 is what caught it.

Search-for-behaviour vs search-for-filename, and the live probe that catches it: [`worked-examples.md`](references/worked-examples.md) §1.

- Framework-defined filenames are **version-dependent**. Check the convention for the version in
  `package.json` before reading absence of a file as absence of a mechanism.
- Prefer searching for **behaviour** (a distinctive identifier, constant, call) over a
  **filename**. Behaviour survives renames; filenames do not.
- When a source-only reading concludes something is exposed, **probe before reporting**. Use a
  read-only endpoint; never let the probe be the exploit.
- "No file named X" is not "no such mechanism", and the gap between those sentences is where this
  failure lives. More source reading cannot escape it — only reality can.

## A check that enumerates a fixed set goes stale silently

> Structural limit 2 of three. **Limit 1** (`.gitignore` as a silent scope reducer) and
> **Limit 3** (a production check is only worth its contract) are in
> `.harness/lesson-patterns.md`. Shared shape: each produces a clean result from a check that was
> not looking at the thing you believed it was looking at.

**Any check that enumerates the surface it guards will eventually guard less than its name says
— and it will not tell you.** The list is right the day it is written and wrong from the first
addition afterwards. Nothing goes red. The suite stays green while covering less.

**Where it was found, 2026-08-01/02 — note the trend in consequence:**

| Check | Fixed set | What it stopped covering |
|---|---|---|
| navigation detector | `href=`, `fetch(`, `router.push` spellings | computed `<Link href={expr}>` |
| C12 entry pages | four listed pages | any page added later |
| auth suite pages | four listed pages | any page added later |
| **auth suite API routes** | **one route** | **`/api/command-centre/provider-usage`, live, no coverage at all** |
| C12 freshness inputs | four source roots | a new top-level source directory |

The fourth row is the one to sit with. That check exists **because** an anonymous-access hole
reached production behind a service-role client — and as written it would not have noticed the
next one. **A control built to close a hole should be the last place a fixed list survives.**

**The rule.** Derive the set; do not list it. Walk the route tree, filesystem or registry —
whatever defines the surface in reality — and let the check grow on its own.

**Two obligations, because discovery has its own failure mode:**

1. **A positive control that the discovery is non-empty.** A broken walk returns zero items, and
   zero items means every per-item assertion silently does not exist — a green run over nothing.
2. **A control that a NEW surface is picked up without editing a list.** Plant a page and a
   route, assert coverage grows, remove them, assert it returns. Without this, "we use discovery
   now" is an assertion about code you changed once. See `C-DISCOVERY` in
   `scripts/prove-controls.sh` — 12 → 14 → 12, observed.

**When a fixed list is legitimate:** when it enumerates the *rules* rather than the *surface* —
tracked-construct regexes, guard patterns, the gate list. Those are the check's own definition.
The test is whether the world can add a member behind your back. It can add a page; it cannot add
a rule.

## CLAIM-SHAPE — a narrowed instrument produces a narrowed claim, mechanically

Mode 7 was written down on 2026-08-02 and **recurred the same day, hours later, by the same
process that wrote it.** Prose did not prevent it. What follows is therefore not advice; it is a
rule about the SHAPE of the sentence you are permitted to write.

**Whenever an instrument is narrowed — for cost, speed, timeout, context or convenience — the
narrowing enters the claim as a qualifier, or the claim is invalid.**

| you ran | the ONLY claim you may write |
|---|---|
| a search over selected paths | "confirmed **within targeted scope**: `<paths>`" |
| a broad search that completed | "confirmed **by discovery**" |
| a search that timed out and was replaced | "confirmed **within reduced scope**; the broad search did not complete" |
| a check that skipped anything | "confirmed **excluding** `<exclusions>`" |

`confirmed by discovery` is reserved for a search that was **not** narrowed and **did** complete.
**Narrowing is legitimate. Reporting it as breadth is not.**

**Mechanical trigger** — any of these means the claim MUST carry a scope qualifier: you replaced
a running search with a faster one; you added `-maxdepth`, `--include`, a path list, `head` or a
`limit`; a command timed out, was backgrounded or killed; you scanned "the file" rather than
"files matching the pattern"; you sampled N of M.

*In one line:* a timed-out broad sweep for `autogit` was replaced by a targeted one, came back
clean, and was reported as "confirmed by discovery". The broad sweep later found
`hooks.json.bak-*` — all four removed hook entries, one copy from re-arming — beside the file
that *was* checked. The narrowing was reasonable; **upgrading the claim to match the intent
rather than the method was the defect.**

**The check to run on your own sentence:** *what did my instrument physically not look at?* If
the answer is anything at all, it goes in the sentence. If you cannot enumerate what was
excluded, you do not know your own scope, and no confirming claim is available to you yet.

## CANARY-PLACEMENT — plant the control on the surface the claim covers

Claim-shape governs the sentence you write after the run. This governs where you put the canary
before it. Same defect at two moments; both are needed, because claim-shape only fires if you
already suspect your scope.

**A positive control must be planted on the surface the claim covers — not on a surface the
instrument is already known to reach.** A canary planted where the instrument demonstrably works
measures nothing you did not already have. It re-proves reachability at a location never in
doubt, and then that PASS gets carried across a boundary it never crossed.

**The two-arm form.** Plant the **same value twice**. Vary **only** the property under suspicion
— directory, extension, tracked-vs-ignored, environment, tenant, branch. One arm lands where the
instrument is known to work (the sanity check on the canary itself); the other lands on the
claimed surface. **A canary detected in arm A and missed in arm B is the finding.** One arm alone
cannot distinguish "the surface is clean" from "the instrument never looked".

*In one line:* "28 `.harness/` files scanned clean with the canary" collapsed under a two-arm
test — arm A in `docs/` DETECTED, arm B in `.harness/` missed, because `secrets_check.py` lists
`".harness/"` in `_SKIP_PATH_PREFIXES` and is structurally incapable of a finding there. Rescanned
with an instrument that reaches them, the files were clean **and** a live-shaped
`TELEGRAM_BOT_TOKEN` was sitting in the blind spot.

**Before planting:** What property do I suspect the instrument is blind to? Does my canary vary
that property and nothing else? Which arm lands on the surface my claim will name? If both arms
detect, my canary proves reachability and **not** cleanliness — the real run still has to happen.
If no placement could have produced a miss, I have not designed a control; I have designed a
formality.

## Naming the risk is not the same as covering it

Sits alongside *"a review is never coverage"* and fails the same way: both mistake an *artefact
about* the work for the work. A gap you wrote down is still open. Writing it down changes who is
surprised, not whether it is exploitable.

*In one line:* my own review brief told the reviewer to check *"arrays of objects"*, and I then
shipped a guard checking only top-level keys — the reviewer found precisely the thing I had
written down. Full account: [`references/worked-examples.md`](references/worked-examples.md) §5.

**Recurred 2026-08-03, and my first diagnosis of it was itself mode 7** — full account in
[`references/worked-examples.md`](references/worked-examples.md) §4. Short version: a claimed
`skills-drift-check` was reported as never built, because `grep` ran over the checked-out tree
while the workflow sat on an unmerged branch. **Built-and-unmerged is worse than never-built:**
it protects nothing while reading as finished. Search every ref (`git grep <name> --all`) before
concluding a control does not exist — and confirm it runs on the branch you care about.

**The tell:** a sentence in a brief, a "revisit if…", a TODO or a known-issues entry, standing
where a check should be. Each is *evidence of awareness* — and awareness is not a control.

**The test:** could this gap be exploited tomorrow by someone who has read the note? If yes, the
note is not a mitigation. Either build the check, or record it as a deferral with a named blocker
and an unblock condition, so the next reader can tell a decision from an intention.

## When the claim is wider than the check, decide WHICH one is wrong

A review saying *"this covers less than you say it does"* has found a mismatch, not a verdict.
**Two different defects produce that sentence.**

- **Mechanism defect** — the check genuinely misses something it should catch. **Fix the check.**
- **Documentation defect** — the check does the right thing; the words promise more. **Fix the
  claim.**

The failure mode is treating every mismatch as the first kind. That is how you extend a check to
make a *word* come true — the same error as adding the next pattern to a detector, aimed at prose
instead of at a regex.

**The test:** ask what a *complete* version of the check would look like. If you can describe and
build it, the check is at fault. If completing it would require something the tool structurally
cannot do — running a browser, submitting live POSTs, predicting unrendered branches — the check
is finished and **the claim is wrong.**

**"Substantially mitigated, with named residue" beats a false "closed."** A bounded, declared gap
is in a different condition from an undiscovered one; only the second is dangerous. A verifier
that overstates itself has failed at its only job, whatever its exit code says.

**Guard against the abuse.** Downgrading a claim to escape a failing check is moving the
goalposts. The test is whether the new claim is *more honest*, not whether it is *easier to
satisfy*. Legitimate downgrades usually arrive alongside the check getting stronger, not instead
of it.
