# Control design failures in full

Moved verbatim from SKILL.md.

## Naming the Risk Is Not the Same as Covering It

Sits alongside **"a review is never coverage"** and fails the same way: both mistake an
*artefact about* the work for the work.

A gap you wrote down is still open. Writing it down changes who is surprised, not whether it
is exploitable.

**Earned 2026-08-02, and the shape is almost comic.** The hardening review brief I authored
told the reviewer to check *"nested objects, arrays of objects"* — and I then shipped a guard
that checked only top-level keys. The reviewer found precisely the thing I had written down.
`proposals` is an array of objects; the entire interesting payload sat one level below where I
was looking. Naming it bought nothing.

**The tell:** a sentence in a brief, a "revisit if…", a TODO, or a known-issues entry, standing
where a check should be. Each is *evidence of awareness* — and awareness is not a control.
`.harness/known-issues.md` is legitimate for a gap that is DEFERRED WITH A RULING; it is not a
place to park a gap you simply have not built.

**The test:** could this gap be exploited tomorrow by someone who has read the note? If yes, the
note is not a mitigation. Either build the check, or record it as a deferral with a named
blocker and an unblock condition — the KI-006/007/008 form — so the next reader can tell a
decision from an intention.

## A Verification That Requires Handling the Thing It Protects Is a Design Failure

**No matter how careful the handling instructions are.**

If a procedure says *retrieve the secret, paste it here, and be careful* — the design is already
wrong. Careful handling is not a control; it is a request that every future operator be careful
every time, and it fails on the day someone is tired, or pastes into the wrong window, or into a
chat with an agent whose transcript is retained.

**The test:** can the verification run without any human ever seeing the value? If not, redesign
the verification, do not improve the instructions.

**Worked example, 2026-08-02.** `KILL_SWITCH_SECRET` was generated straight into Vercel through a
pipe and deliberately never read back — the value existed only in the platform, held by nobody.
That property was the whole point.

The verification then designed to prove it worked asked the founder to **retrieve it from the
dashboard and paste it into a `curl`**. It was pasted into the agent conversation, and the
transcript is exactly the place the design existed to avoid. The secret had to be rotated.

Then the *remediation* repeated the shape: "add the new value to the GitHub Environment" would
have required retrieving and pasting a second time. Caught by the founder, not by me. **A design
failure of this kind recurs in its own fix**, because the instinct that produced it is still
operating.

The correct design was available from the start and costs nothing: **generate once and dual-write**
— one freshly generated value piped into both stores in a single command, so it never surfaces
in either direction and nobody ever holds it.

**The honest part, because the trade-off was real.** The manual probe was recommended *before*
the CI proof for a genuine reason: it is debuggable. One command, immediate answer, no workflow
plumbing, and a clear result you can iterate against. That benefit is real and it is why the
choice felt reasonable.

**It was outweighed, and should have been.** Debuggability is worth a lot, but not a live
credential passing through a human's clipboard and an agent's context. When the convenient path
requires handling the protected thing, the convenience is being purchased with the protection.
Build the plumbing.

## STRUCTURAL LIMIT 2 — a check that knows a fixed set goes stale silently

> One of three numbered structural limits of the evidence apparatus. Index and peers —
> **Limit 1** (`.gitignore` as a silent scope reducer) and **Limit 3** (a production check is
> only worth its contract) — are in `.harness/lesson-patterns.md`. Shared shape: each produces a
> clean result from a check that was not looking at the thing you believed it was looking at.

**Any check that enumerates the surface it guards will, at some point, guard less than its name
says — and it will not tell you.** The list is right the day it is written and wrong from the
first addition afterwards. Nothing goes red. The suite stays green while covering less.

This is the same class as enumerating navigation *forms* (four review rounds, four patterns), and
it is not a tuning problem: **a fixed enumeration cannot notice what it does not contain.**

**Where it was found, 2026-08-01/02 — note the trend in consequence:**

| Check | Fixed set | What it stopped covering |
|---|---|---|
| navigation detector | `href=`, `fetch(`, `router.push` spellings | computed `<Link href={expr}>` |
| C12 entry pages | four listed pages | any page added later |
| auth suite pages | four listed pages | any page added later |
| **auth suite API routes** | **one route** | **`/api/command-centre/provider-usage`, live, with no coverage at all** |
| C12 freshness inputs | four source roots | a new top-level source directory |

The fourth row is the one to sit with. That check exists **because** an anonymous-access hole
reached production behind a service-role client — and as written, it would not have noticed the
next one. **A control built to close a hole should be the last place a fixed list survives.**

**The rule.** Derive the set; do not list it. Walk the route tree, the filesystem, the registry —
whatever defines the surface in reality — and let the check grow on its own.

**Two obligations that come with it, because discovery has its own failure mode:**

1. **A positive control that the discovery is non-empty.** A broken walk returns zero items, and
   zero items means every per-item assertion silently does not exist. That is a green run over
   nothing — the same shape as a scan that reads no blobs.
2. **A control that a NEW surface is picked up without editing a list.** Plant a page and a route,
   assert coverage grows, remove them, assert it returns. Without this, "we use discovery now" is
   an assertion about code you changed once. See `C-DISCOVERY` in `scripts/prove-controls.sh` —
   12 → 14 → 12, observed.

**When a fixed list is legitimate:** when it enumerates the *rules* rather than the *surface* —
the tracked-construct regexes, the guard patterns, the gate list. Those are the check's own
definition. The test is whether the world can add a member behind your back. It can add a page; it
cannot add a rule.

## When the Claim Is Wider Than the Check, Decide WHICH One Is Wrong

A review that says *"this covers less than you say it does"* has found a mismatch, not a
verdict. **Two different defects produce that same sentence, and telling them apart is the
skill.** Get it wrong and you either ship an overclaim or grind forever.

- **Mechanism defect** — the check genuinely misses something it should catch. **Fix the check.**
- **Documentation defect** — the check does the right thing; the words around it promise more.
  **Fix the claim.**

The failure mode is treating every mismatch as the first kind. That is how you end up extending
a check to make a *word* come true — the same error as adding the next pattern to a detector,
aimed at prose instead of at a regex.

**Worked example, 2026-08-01/02, navigation coverage (G1).** Four review rounds all reported the
claim being wider than the check. They were not the same finding:

| Round | What was wrong | Right fix |
|---|---|---|
| 1 | no timeouts; stale build passed; query strings dropped | **check** — real misses |
| 2 | only slash-prefixed hrefs matched, so relative links unmeasured | **check** — real miss, fixed by RESOLVING urls rather than adding a pattern |
| 3 | redirect-to-missing passed green; freshness walk too narrow | **check** — real misses |
| 3 | *"G1 is CLOSED"* over a mechanism the reviewer called sound | **claim** — downgraded to *substantially mitigated, with named residue* |

Round 3 carried both kinds at once, which is why it needs reading carefully rather than
actioning in one direction.

**The test for which one you have:** ask what a *complete* version of the check would look like.
If you can describe it and build it, the check is at fault. If completing it would require
something the tool structurally cannot do — running a browser, submitting live POSTs, predicting
unrendered branches — then the check is finished and **the claim is what is wrong.**

**"Substantially mitigated, with named residue" is a better outcome than a false "closed."** A
bounded, declared gap is in a different condition from an undiscovered one; only the second is
dangerous. Honest descriptions are the product a verifier exists to produce — a verifier that
overstates itself has failed at its only job, whatever its exit code says.

**Guard against the abuse.** Downgrading a claim to escape a failing check is moving the
goalposts. The test is whether the new claim is *more honest*, not whether it is *easier to
satisfy*. Legitimate downgrades usually arrive alongside the check getting stronger, not instead
of it.

## The First Run of a New Control Is the FAILING One

**Rule: a new check is not trusted until it has been observed to FAIL — and to fail for the
reason you think.** Write it, aim it at a defect you have planted, and watch it go red. Only
then aim it at the real system. A control whose first observed state is green has been tested
for its ability to agree with you.

**Verify the failure, not just the exit code.** "It failed" is not enough — read the message and
confirm it names the planted defect. Four of the misfires below "failed" or "passed" for a
reason entirely unrelated to what was being tested.

**Controls fail toward green, and the bias is directional, not random.** On 2026-08-01/02, four
control mis-designs in one session, **all four green**:

| # | Control | What went wrong | Read as |
|---|---|---|---|
| 1 | review tree-integrity | planted file at `*.tmp`, covered by `.gitignore` repo-wide | "no mutation" |
| 2 | secrets-scan coverage | planted secret in `.md`, which is in `_SKIP_EXTS` | "no secrets" |
| 3 | build-freshness | exit code measured through `\| head`, so it reported head's 0 | "control passed" |
| 4 | route-exercise | attached to an orphaned server serving the **previous** build | "no broken route" |

Plus a fifth in the tool built to check for exactly this: a history scanner whose input paths all
carried a stray `\r`, so it read **0 blobs** and printed "no secrets found" over 6160 paths.

Five of five landed on green. That is not chance — you write a test expecting it to pass, so
every accident lands on the side you expected. **Assume your control is green because it is
broken until you have seen it red.**

**The one that went the other way, and why it does not soften the rule.** A sixth misfire
reported FAIL against a *working* scanner: the check ran `scanner | grep -q`, and the scanner
exits 1 when it finds a violation — the success case — so under `set -o pipefail` the pipeline
was non-zero even though grep matched. A false RED. It cost ten minutes and was self-correcting,
because a red result gets investigated. **The asymmetry is the point: a false green is never
investigated, because nobody audits good news.** Both are bugs; only one is dangerous.

Three habits that catch all five:
- **Plant the defect where the check must look**, not merely nearby. Check the ignore rules, the
  extension filters and the path prefixes of the thing you are testing *first*.
- **Never measure an exit code through a pipe.** `cmd > file; echo $?`, never `cmd | head`.
- **Assert the scan did work**: blobs read > 0, files scanned > 0, paths exercised > 0. A checker
  that examined nothing must fail, not pass.

## A SERVICE THAT INVENTS ITS OWN CREDENTIAL HAS NO FAILURE MODE — IT HAS A SILENT RECONFIGURATION MODE

```python
if not _raw_password:  _raw_password = secrets.token_urlsafe(24)   # app/server/config.py
...
else: SESSION_SECRET = secrets.token_hex(32); _SECRET_FILE.write_text(SESSION_SECRET)
```

When `TAO_PASSWORD` is unset the server generates a random password, logs it once, and
persists a bcrypt hash. Same for `TAO_SESSION_SECRET`. This is usually written as convenience —
"so it still boots" — and it is the most dangerous shape a missing-config branch can take.

**A missing credential is a loud, diagnosable fault. An invented one is not a fault at all.**
The service starts, reports healthy, and rejects every legitimate client. Nothing anywhere logs
an error, because from the service's point of view nothing went wrong. The symptom appears at
the *caller*, as an authentication failure, which routes the investigation to the caller's
credential — the one thing that is not broken.

Worse with ephemeral storage: persistence is to a container filesystem, so **a redeploy can
rotate the credential to a value nobody holds**, at a moment unrelated to any change anyone
made. It presents identically to a stale password, and it is unfalsifiable from the client side.

**The correct behaviour is refuse-to-start.** A service that cannot authenticate anyone should
not accept connections; an unavailable service is diagnosable in seconds and an inaccessible one
is not. Auto-generation is defensible only for a genuinely single-user local dev default, and
even then it must be impossible in a deployed environment.

*Recorded 2026-08-02 as a proposal, not a change.* Whether the Pi CEO upstream actually had
`TAO_PASSWORD` unset was never established — Railway was not reachable from the diagnosing
machine. The finding stands on its own regardless of whether it fired here: the branch exists,
and while it exists this fault is always available.
