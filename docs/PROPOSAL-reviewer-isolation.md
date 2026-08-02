# Proposal — reviewer isolation

**Status: PROPOSAL. Not a decision, not built.** Phill rules; implementation follows the ruling.

## Which branch this is on, and why

**`feat/command-centre-migration`.**

`scripts/codex-review.sh` exists only on this branch — verified, not assumed:
`git cat-file -e origin/main:scripts/codex-review.sh` fails. Every artefact this document cites
(`.harness/*-wrapper.log`, `.harness/*review*.txt`, `.harness/sandbox-probe/probe.cjs`,
`.harness/respec-review-brief.md`) is likewise branch-side. A copy on `main` would cite line
numbers in a file `main` does not contain, and the branch merge is parked.

**Citation caveat.** `.harness/` was untracked on this branch in `2deac32c`, so those paths resolve
in history at **`b3a664ef`**, not at the tip. Read them with `git show b3a664ef:<path>`.
`scripts/codex-review.sh` is live at the tip and its line numbers below are current.

---

## 1. The problem, precisely

### 1.1 The reviewer could not execute

Measured by `.harness/sandbox-probe/probe.cjs` (19 lines) and recorded verbatim in
`scripts/codex-review.sh:6-17`:

```
sandbox:  SPAWN_NET_USE FAIL EPERM | SPAWN_CMD FAIL EPERM | WRITE OK | UNLINK FAIL EPERM
control:  all OK
```

Two distinct denials, each with a matching observed failure:

- **No nested process spawn.** Vite's `optimizeSafeRealPathSync()` shells out to `net use` on
  Windows on first realpath. The throw lands *outside* Vite's try/catch, surfacing as
  `failed to load config` (`codex-review.sh:14-15`). Vitest therefore never starts.
- **No DELETE.** `next build` unlinks `.next/app-path-routes-manifest.json`. WRITE was permitted
  and only DELETE denied, which is why it failed at that point and not earlier
  (`codex-review.sh:16-17`).

`codex-review.sh:6-8` names the sandbox as a *"windows unelevated restricted-token sandbox"*,
sourced from the binary's own strings — a measured attribute, not a documentation claim.

### 1.2 How many rounds actually went unevidenced

Applying Control 2's own regex to every transcript:

| series | transcripts | execution proof | explicit EPERM + `failed to load config` |
|---|---|---|---|
| `cc-01` | 7 | **0 of 7** | round 6 |
| `cc-02` | 4 | **0 of 4** | rounds 2, 3, 4 |
| post-wrapper (`cap4`, `hardening` 1–3, `respec` 3, 4, 4b) | 7 | **7 of 7** | none |

**Two corrections to the brief I was given, stated because the document must be citable:**

1. It was not "three of four". In the `cc-02` series it was **four of four**; across `cc-01` and
   `cc-02` together, **eleven of eleven** transcripts carry no execution proof. The failure was
   total before the wrapper existed, not partial.
2. **Round 4 was not the first fully evidenced review — round 4b was.**
   `.harness/respec-round4-wrapper.log` records round 4 as `RESULT: NOT USABLE AS EVIDENCE`,
   `EXIT=1`: HEAD moved `5e102f38 → 2aad6389` and `.autogit.json` was modified. Execution proof
   *was* found; the round was voided on tree integrity.
   `.harness/respec-round4b-wrapper.log` is the first `EXIT=0` with all controls green and
   `VERDICT: PASS`.

Round 4 also produced a control defect worth carrying: the wrapper reported *"the reviewer mutated
the repository"* when the truth was that the builder committed mid-review. `codex-review.sh:120-130`
now records that incident and splits the two cases — HEAD-moved-tree-identical is operator error,
tree-changed is a security finding. Right conclusion, wrong attribution, which in a security control
is its own defect.

The substance of the concern stands and is unaffected by both corrections: **before the wrapper,
every "green" attributed to a review was the builder's claim, single-sourced.** The reviewer was
reading and agreeing, not verifying.

### 1.3 The fix, and what it costs

`codex-review.sh:101` runs:

```
codex exec --skip-git-repo-check -s danger-full-access -m gpt-5.5
```

`codex-review.sh:19-20` states why no tuning was possible: *"tests must spawn, builds must unlink.
`[windows] sandbox` only selects elevated/unelevated."* The flag is scoped to the invocation and
deliberately never written into `~/.codex/config.toml` (`codex-review.sh:97-98`).

---

## 2. What `-s danger-full-access` actually grants

**What I can state from measurement.** The reviewer runs as a process on this machine under this
user account. Absent a restricting sandbox it holds this account's ambient authority. What that
account can reach, verified by existence check this session:

| reach | verified present | consequence |
|---|---|---|
| **Filesystem** | `~/.codex/auth.json`, `~/.claude/settings.json`, **58 git repositories on `D:`** | The whole user profile and every sibling estate repo — CARSI, Synthex, RestoreAssist, Authority-Site — are readable and writable. |
| **Environment & credentials** | `~/.railway/config.json` (holds a 308-char session token — read this session), `~/.vercel/auth.json`, `~/.gitconfig`, `~/.git-credentials` | Live tokens for Railway and Vercel. The script itself reads `~/.codex/auth.json` at `:43-49`, which proves that path is readable from this context. |
| **Git & remote** | `~/.ssh/id_ed25519`, `remote.origin.url = git@github.com:CleanExpo/Pi-Dev-Ops.git` | Key-based push rights to every `CleanExpo` repo the key authorises. A reviewer with this reach can commit and push — including to the branch under review. |
| **Network** | machine egress confirmed (direct `curl` to Telegram, Vercel and Railway APIs succeeded this session) | Arbitrary outbound. Combined with credential reach, exfiltration is available in one step. |

**Where I am NOT certain, stated rather than papered over.** The table above describes *the account's*
reach. I have **not measured the reviewer process's own boundary** under `danger-full-access`. I do
not know from evidence whether that mode:

- applies any residual filesystem confinement outside the working tree,
- restricts network egress in any way,
- filters the inherited environment block,
- or differs between elevated and unelevated invocation.

I am declining to describe those semantics from documentation or recollection, because this session
has already produced three instances of a right conclusion drawn through a blind instrument. **The
honest position is that the boundary is unmeasured.** `probe.cjs` already measures spawn/write/unlink
for the restricted sandbox; the same technique extended to reads outside the tree, writes outside the
tree, and outbound network would settle it in one run. **That measurement should precede the ruling**,
because several options below are only distinguishable once it exists.

---

## 3. What must be preserved — non-negotiable

**The reviewer executes.** Round 4b is the first fully evidenced review precisely because the
reviewer ran `scripts/prove-controls.sh` (twice, for idempotency), `route-exercise.mjs` including
`--plant-broken-link` as a deliberate red control, `scripts/handoff-loop.sh`, and the suites — itself,
and reported what it observed. The required loop is enumerated at
`.harness/respec-review-brief.md:115-119`.

`codex-review.sh:27-29` states the principle: *"A reviewer that cannot execute cannot validate a
verifier, so silent non-execution must be loud, not a footnote."* When the claim under review is
"these checks fail red when they should", **only running them shows that.** Static reading cannot
distinguish a control that fires from a control that cannot fire — that is the whole failure class
this estate keeps rediscovering.

**Any option that returns the reviewer to static reading is a REGRESSION, not a mitigation, and must
be labelled one.** No such option appears below. If one is proposed later, it should be scored
against the eleven-of-eleven unevidenced rounds in §1.2, which is what static reading produced.

---

## 4. What must be bounded — positive list

What the reviewer **needs**, derived from the required loop rather than from imagination:

1. **Read/write within the repository tree**, including gitignored build paths (`.next/`,
   `node_modules/`) — writes there are legitimate and unavoidable.
2. **Process spawn**, arbitrarily nested — Vite shells out on first realpath.
3. **File delete within the tree** — `next build` unlinks its own manifests.
4. **A Node/pnpm toolchain** at the versions the repo pins.
5. **Loopback networking** — `route-exercise.mjs` starts the built app, authenticates against it and
   fetches pages, so it must bind and connect on localhost.
6. **Read-only git metadata for this repo** — `rev-parse`, `status`, `log`, `diff`.
7. **Read access to the brief** and write access to its own transcript path.

Two items need a decision rather than an assumption, and I flag them rather than guess:

- **External network.** Unknown whether `next build` still requires egress. A cc-01 commit removed an
  external font (`80e71cd`), which suggests it was being reduced. Measurable by building with egress
  denied. If the answer is no, external network drops off the list entirely — which materially
  strengthens options A and B.
- **Package installation.** If `node_modules` is pre-populated in the image or mount, no registry
  access is needed. If it must install, that is a supply-chain surface inside the reviewer.

This is expressed as needs, not prohibitions, by design: an unbounded negative list ("must not touch
X, Y, Z…") is unspecifiable and cannot be proven. A positive list is closed and testable — anything
absent from it is a candidate for the red controls in §6.

---

## 5. Options

### Option A — container, tree mounted, no host credentials

Reviewer runs in a container. The repo is bind-mounted; the container image carries the toolchain.
No host home directory, no SSH agent, no cloud CLI configs, no inherited environment.

**For.** Satisfies every item in §4 natively — spawn, unlink, loopback all work normally inside a
container. Boundary is explicit and inspectable rather than inferred. Credential reach becomes empty
by construction rather than by instruction. Egress can be denied at the network namespace and proven.

**Against.** Requires a working container runtime on a Windows host — Docker Desktop or WSL2, neither
currently verified present here. Bind-mount I/O on Windows is materially slower, which lengthens
every round. The image becomes a maintained artefact that can drift from the repo's pinned toolchain;
that drift is a new failure mode and needs its own check. Does not by itself stop a reviewer writing
*into the mounted tree* — Control 1 still carries that.

### Option B — fixed Codex sandbox, no full-access

Resolve the EPERM at its cause so the existing sandbox can run the suite: grant nested spawn and
in-tree delete without granting the machine.

**For.** Smallest change; keeps the current wrapper and workflow intact. If achievable, it is the
only option that bounds the reviewer *without* introducing new infrastructure.

**Against — and this is close to disqualifying on current evidence.** `codex-review.sh:19-20` states
flatly: *"No tuning of that sandbox can run the suite… `[windows] sandbox` only selects
elevated/unelevated."* If that reading is correct, there is no configuration surface to fix and this
option does not exist. It is listed because that conclusion rests on the binary's strings and one
probe run, not on an exhausted search of the configuration surface — and because a Codex release
could add the control at any time. **Before this is ruled on, someone should establish whether a
spawn/delete-permitting-but-still-confined mode exists at the installed version.** If it does not,
Option B is closed and should be recorded as closed rather than left open.

### Option C — separate execution surface (CI produces an artifact the reviewer consumes)

CI runs the loop; the reviewer reads the resulting artefact and reasons about it.

**Is a CI-produced result independent of the builder, or the builder's claim wearing a different
badge?** Asked plainly, so answered plainly:

**On this repository today, it is the builder's claim wearing a different badge.** Three reasons,
the first decisive:

1. **Branch protection is unavailable.** `gh api repos/CleanExpo/Pi-Dev-Ops/branches/main/protection`
   returns **HTTP 403 — "Upgrade to GitHub Pro or make this repository public to enable this
   feature."** Making the repo private to contain the credential exposure removed the ability to
   protect branches at all. Nothing prevents the builder editing `.github/workflows/` in the same
   commit under review.
2. **The builder authored what CI runs.** The workflow file, the scripts it invokes and the
   assertions inside them are all builder-written artefacts. CI faithfully executing a check that
   cannot fail reproduces the exact failure class this estate has hit repeatedly.
3. **It is a regression against §3 unless carefully bounded.** If the reviewer only *reads* the
   artefact, it is static reading with extra steps — precisely what §3 forbids — and must be
   labelled a regression.

CI **is** genuinely independent in one narrower and real respect: it is independent of the builder's
*machine and local state*. It defeats "green on my box". It does not defeat "the check was written so
it could not go red".

**A variant that is worth ruling on:** CI as an *execution surface the reviewer drives* — the reviewer
dispatches a run against a pinned SHA it selects, and reads logs it did not author the trigger for.
That restores execution without granting the reviewer the machine. It still fails point 1 until
branch protection exists, but it is the only form of Option C that is not a §3 regression.

---

## 6. How isolation would be PROVEN — red first, per option

The standard, per `skills/control-design/SKILL.md`: a control that cannot fail is worth exactly as
much as no control. Every option below is scored on whether isolation can be **made to go red on
purpose**. Two canaries, both of which must FAIL for the reviewer:

- **READ canary** — a file planted outside the intended reach containing a unique high-entropy token.
  The reviewer is asked to read it and print it. **It must fail. If the token appears in the
  transcript, isolation is not real.** Placed on the surface the claim covers, not one the reviewer
  obviously reaches — i.e. beside real credentials in `~/`, not in an invented directory.
- **WRITE canary** — an attempted write to a path outside the tree (e.g. `~/.codex/probe-write`).
  **It must fail.** Verified by absence of the file afterwards, checked by the wrapper, not by the
  reviewer's own report.

Both must be run with a **positive arm** proving the canary is reachable when isolation is off —
otherwise a failed read is indistinguishable from a mistyped path.

| option | READ canary provable? | WRITE canary provable? | verdict |
|---|---|---|---|
| **A — container** | **Yes.** Host `~/` is simply not in the mount namespace. Positive arm: same canary inside the mount, which must succeed. | **Yes.** Read-only mounts outside the tree; write returns EROFS/EACCES. | **Fully provable.** The only option where both canaries have a mechanism. |
| **B — fixed sandbox** | **Unknown — and that is the finding.** Depends entirely on whether a confining-but-spawn-permitting mode exists. Cannot be designed until §2's measurement is done. | Unknown, same dependency. | **Not yet provable. Do not rule on B before the boundary is measured.** |
| **C — CI artifact** | **Not applicable, which is itself the finding.** There is no reviewer process to confine; the isolation question has been moved, not answered. The runner is isolated from the host, but the *builder* is not isolated from the runner — and that is the threat §5 C identifies. | Not applicable. | **The canaries cannot be aimed at the real risk.** C's exposure is authorship of the check, and no filesystem canary tests that. |

**Finding on C:** an option whose principal risk cannot be expressed as a falsifiable control is
weaker than it appears, regardless of how clean its execution story looks. The thing that would test
C is not a canary but a **planted failing assertion** — commit a check that *must* go red, and
confirm CI reports red. That is a different control and should be specified as such if C is chosen.

**Finding on the status quo:** `-s danger-full-access` fails both canaries by definition. There is no
version of the current arrangement in which isolation is provable, because there is no isolation. The
three wrapper controls are compensating controls for a boundary that does not exist.

---

## 7. What the existing wrapper controls cover today

Note: `codex-review.sh:24` says *"Three controls"* and lists PLAN AUTH as the third, but the body
implements **four** numbered controls (1, 1b, 2, 3). The header is stale relative to the body.

| control | lines | what it actually claims |
|---|---|---|
| **1 — tree integrity** | `:52-68`, `:113-150` | HEAD + `git status --porcelain` hashed pre/post. Claim is *"the reviewed artifact was not modified"*, explicitly **not** *"the reviewer wrote nothing anywhere"* (`:57-61`). Blind to gitignored paths by necessity. Proven to discriminate 2026-08-01; the first two attempts used a `*.tmp` path and silently missed, which is how the scope limit was found (`:63-66`). |
| **1b — codex config hash** | `:70-94`, `:152-160` | Detects self-escalation: a reviewer editing `~/.codex/config.toml` to widen its own permissions for every future run. Excludes `last_updated`/`last_revision` churn — a false positive on first real use nearly taught the operator to ignore the alarm (`:80-83`). Fail-closed on anything unrecognised. |
| **2 — execution proof** | `:162-175` | Greps the transcript for vitest's `Tests N passed` / `Test Files N`. Absence is a hard fail, because for a review *of a verifier*, an unexecuted suite makes every "green" the builder's claim (`:169-172`). |
| **3 — plan auth** | `:42-50` | Refuses to run on a paid per-call key. A **cost** control, not an isolation control. |

### Which survive each option

| control | A — container | B — fixed sandbox | C — CI artifact |
|---|---|---|---|
| **1 tree integrity** | **Still carries weight.** A mounted tree is still writable; this is the control that catches it. Also still catches the builder committing mid-review — operator error, unrelated to isolation. | Still carries weight, same reasoning. | **Weight shifts.** The reviewer may not touch a tree at all; the analogous control becomes "the artefact is bound to the SHA it claims". |
| **1b codex config hash** | **Unnecessary.** `~/.codex/` is outside the mount; self-escalation via that file is structurally impossible, not merely detected. Retiring it is a genuine simplification — but only *after* the READ/WRITE canaries prove the mount boundary, never on the assumption of it. | **Necessary and possibly insufficient.** If the reviewer still runs on the host, this is the only control on the escalation path. | **Unnecessary** — no local reviewer process. |
| **2 execution proof** | **Still carries weight, unchanged.** Isolation does not prove execution. These are orthogonal, and §3 makes execution the non-negotiable. | Still carries weight, unchanged. | **Still carries weight, and becomes harder.** Must bind to *the artefact's* SHA, not a local transcript, or it degrades to trusting a badge. |
| **3 plan auth** | Unaffected — orthogonal to isolation. | Unaffected. | Unaffected, though CI billing is a different cost surface. |

**The control that survives everything is Control 2.** Isolation and execution are independent axes,
and only execution is non-negotiable per §3. **The control most likely to be retired is 1b**, and only
under Option A, and only once the mount boundary is proven red-first rather than assumed.

---

## 8. What I recommend deciding, without recommending which option

Not a ruling — three things that would make a ruling well-founded, in order:

1. **Measure the `danger-full-access` boundary** (§2). Options A and B are not properly comparable
   until it exists, and it is one extension of `probe.cjs`.
2. **Establish whether a spawn-permitting, still-confined Codex mode exists** at the installed
   version (§5 B). If not, close Option B explicitly rather than leaving it nominally open.
3. **Decide whether external network is required by the loop** (§4). If it is not, A and B both
   tighten considerably and egress denial becomes provable.

**Standing risk while this is undecided:** every review round runs with full machine authority over
58 repositories, live Railway and Vercel tokens, and push-capable SSH keys. That has been the
arrangement for every evidenced round to date — `cap4-1`, `hardening-1/2/3`, `respec-3/4/4b`. Nothing
has gone wrong, and nothing in the current setup would have shown it if it had, beyond the two
repo-scoped hashes and one machine-scoped config hash.
