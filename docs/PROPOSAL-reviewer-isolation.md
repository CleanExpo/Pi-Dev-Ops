# Proposal — reviewer isolation

**Status: §1–8 PROPOSAL. §9 SPECIFICATION, ruled 2026-08-03 — Option A (container). Not built.**

**Option B is CLOSED on measurement**, not on reasoning — see §9.0. Option C remains a regression
against §3 while branch protection is unavailable (§5 C). Phill ruled A; §9 specifies it. Nothing in
§9 has been implemented.

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

---

# 9. Container specification

Ruled 2026-08-03. **Specification only — not built.**

## 9.0 The measurement that closed Option B

Two arms, same probe (`.harness/sandbox-probe/probe-boundary.cjs`). Arm A direct; Arm B inside
`codex exec --skip-git-repo-check -s danger-full-access -m gpt-5.5` — the exact invocation at
`codex-review.sh:101`. Arm A passing everything is what makes an Arm B refusal meaningful.

| check | Arm A | Arm B (inside reviewer) |
|---|---|---|
| `SPAWN_NET_USE` / `SPAWN_CMD` | OK / OK | **OK / OK** |
| `WRITE_IN_TREE` / `UNLINK_IN_TREE` | OK / OK | **OK / OK** |
| `READ_OUTSIDE_TREE` (`~/.gitconfig`) | OK 636 B | **OK 636 B** |
| `READ_CREDENTIAL[.railway/config.json]` | READABLE 747 B | **READABLE 747 B** |
| `READ_CREDENTIAL[.codex/auth.json]` | READABLE 4558 B | **READABLE 4558 B** |
| `READ_CREDENTIAL[.ssh/id_ed25519]` | READABLE 387 B | **READABLE 387 B** |
| `WRITE_OUTSIDE_TREE` | OK, landed | **OK, landed** |
| `SIBLING_REPOS_VISIBLE` | 58 | **58** |
| `NETWORK` | HTTP 200 | DNS OK · TCP 443 OK · HTTP 200 |

**`danger-full-access` applies no filesystem, credential or network boundary.** Both §6 canaries
fail: the read outside reach succeeds and the write outside the tree succeeds. There is no partial
confinement to tune toward, so B is closed.

*One near-miss recorded because it is the point of this document.* Arm B first returned
`NETWORK_OUTBOUND: FAIL UNABLE_TO_VERIFY_LEAF_SIGNATURE`, which reads like a block. It is not — my
shell carries `NODE_EXTRA_CA_CERTS` and codex's environment does not. A separate discriminator
(`net-discriminator.cjs`) settled it: DNS resolves, TCP/443 connects, plain HTTP returns 200. Egress
is open. Reporting the first result would have invented a boundary that does not exist.

## 9.1 The constraint that shapes the design

**Egress cannot be closed. The reviewer talks to a hosted model by construction** — a reviewer with
no network is not a reviewer. Network is therefore *not* the boundary and must not be relied on as
one. **The mount is the boundary, and it carries all of the weight.**

Two consequences, stated so no one later mistakes the design for defence-in-depth it does not have:

1. An egress *allowlist* is a mitigation, not a boundary. If the runtime supports per-host egress
   control it should be used (§9.3), but the design must remain sound if it is bypassed.
2. Because exfiltration is always available to a process that can reach the model endpoint,
   **anything readable inside the container is effectively disclosed.** The mount list is therefore
   a disclosure list. That is the correct way to review it.

## 9.2 External network the loop actually needs — measured

Beyond the model endpoint:

| need | verdict | how established |
|---|---|---|
| **Google Fonts (`fonts.gstatic.com`)** | **REQUIRED on a cold cache** | Three independent lines: `next/font/google` imported in `app/layout.tsx:4` and two `command-centre` pages; `fonts.gstatic.com` resolved during a measured run; **38 `.woff2` files emitted into `.next/static/media/`**. |
| **Package registry** | **NOT required by the default loop** | `npm ci` sits behind `--full` (`handoff-loop.sh:61`); `dashboard/node_modules` is pre-populated (412 entries). **But a fresh container has no `node_modules`** — see §9.3. |
| **`git fetch` / remote git** | **NOT required** | No `git fetch/pull/clone/ls-remote` in `prove-controls.sh`, `route-exercise.mjs` or `handoff-loop.sh`. |
| **Supabase (`lksfwktwtmyznckodsau.supabase.co`)** | **OBSERVED, NOT ATTRIBUTED** | Resolved during the run and passed as a build env var (`prove-controls.sh:186`), but the DNS cache is polluted by ambient traffic (Tailscale, AVG, Windows, this session). I cannot separate loop traffic from machine traffic with this instrument. **Treat as required until measured properly** — inside a container the cache is clean and this resolves itself on first run. |
| **`x.invalid`** | must FAIL to resolve | Deliberate fail-closed fixture (`prove-controls.sh:186`). It must keep failing; an egress allowlist that somehow resolved it would break the control. |

Measurement limit, stated: DNS-cache diffing on a shared host cannot attribute a resolution to a
process. The container makes this trivially measurable and the first run should re-establish it.

## 9.3 What is mounted

**Principle: the source of record is read-only; only generated paths are writable.** This converts
Control 1 from detective to *preventive* for tracked source — a reviewer write to source fails at the
syscall rather than being caught afterwards.

| path | mode | why |
|---|---|---|
| repo tree → `/work` | **read-only** | §4.1 read access. Tracked source must not be writable. |
| `/work/.git` | **read-only** | §4.6 `rev-parse`, `status`, `log`, `diff`. Read-only removes commit/push capability structurally. |
| `/work/dashboard/.next` | **read-write volume** | §4.1/4.3 build must write and unlink here. |
| `/work/dashboard/node_modules` | **read-write volume**, pre-populated in the image | §4.4 toolchain. Baking it in removes the registry from the runtime path entirely. |
| `/work/.harness/<transcript>` | **read-write**, single file | §4.7 the reviewer's own output. |
| brief file | **read-only** | §4.7. |
| model credential | **read-only, single file** | §9.4. |

**Not mounted — the disclosure list, inverted:**

`~/.ssh/` (any key) · `~/.railway/config.json` · `~/.vercel/` · `~/.gitconfig` ·
`~/.git-credentials` · `~/.claude/` · `~/.codex/config.toml` · the host `$HOME` generally ·
**any path on `D:\` other than this repo** (58 repos are currently reachable; the correct number is
1) · the container runtime socket · the host process namespace.

**Environment: explicit allowlist, nothing inherited.** `PATH`, `HOME`, `CI`, `NODE_ENV`, plus the
build vars `prove-controls.sh:186` sets for itself. Arm B already showed the reviewer's env differs
from the shell's (`VERCEL_TOKEN` absent) — that is incidental, not a control, and must become one.

**Writable-set caveat requiring measurement, not assumption.** A read-only source tree may break the
build if Next writes into it (`next-env.d.ts`, `*.tsbuildinfo`). **Do not guess the list.** First run:
mount source read-only, run the loop, collect every `EACCES`/`EROFS` path, and promote exactly those
to named writable volumes. Any path promoted this way is a documented exception with a reason.

**Egress:** allow the model endpoint and `fonts.gstatic.com`; add Supabase if §9.2 confirms it.
If the runtime cannot do per-host egress control, that is a finding to record — not a blocker,
because per §9.1 egress is not the boundary.

## 9.4 Model authentication — and a tension that needs a ruling

The reviewer must authenticate to the model **without holding a credential that opens anything else.**

**Specified:** mount `~/.codex/auth.json` **read-only, as a single file**, at its expected path.
Nothing else from `~/.codex/` — notably **not** `config.toml`, which is the self-escalation path
Control 1b exists for (§9.6).

**The tension, surfaced rather than resolved because it is a spend decision.** Control 3
(`codex-review.sh:42-49`) *requires* plan auth (`auth_mode=chatgpt`) and refuses to run on a paid
per-call key. So the only credential the design may use is a **full ChatGPT account credential**
(4558 bytes) — which is precisely a credential that opens something else. Per §9.1, mounting it means
disclosing it.

Two ways out, both Phill's to choose:

- **(a) Accept it.** Keep plan auth; the reviewer can read the account credential. Cost stays zero.
  Residual risk: account compromise, not estate compromise — no SSH key, no cloud tokens, no other
  repos. This is a large reduction from today even though it is not zero.
- **(b) Scoped API key.** A dedicated key, one project, hard spend cap, injected as an env var rather
  than a mounted file. It opens **only model inference** — the property §9.4 asks for. **Requires
  amending Control 3**, which currently forbids exactly this, and introduces per-call spend.

### 9.4.1 RULING — option (a), recorded as ACCEPTED EXPOSURE PENDING REMEDIATION

**Ruled by Phill, 2026-08-03. Status: `accepted-exposure-pending-remediation`.**

| field | value |
|---|---|
| **Exposure accepted** | The reviewer can read `~/.codex/auth.json` (4558 B), a full ChatGPT account credential, mounted read-only. Per §9.1 anything readable inside is effectively disclosed. |
| **Rationale** | Blast radius moves from *the estate plus a production deploy path* — 58 repos, `~/.ssh/id_ed25519`, Railway and Vercel tokens, push-capable remotes — down to **one SaaS account**. Zero spend, no governance change. |
| **Residual risk** | Account compromise. **Not** estate compromise: no key material, no cloud tokens, no other repository, no deploy path. |
| **Remediation** | **§9.4.2 credential broker.** Specified below, not an intention. Build work, sequenced after the container proves out per §9.5. |
| **Review trigger** | Container passes §9.5; or any change to what `auth.json` grants; or the credential's scope widens. |
| **Expiry** | Not open-ended. Revisit at the §9.5 gate. |

**This acceptance is NOT an endorsement of amending Control 3.** Control 3 (`codex-review.sh:42-49`)
is a **spend-posture** control — it refuses paid per-call keys. Whether the estate takes on per-call
model spend is a financial decision on its own merits and its own timeline. **It must not ride along
as a side effect of an isolation decision.** Option (b) remains available and un-chosen; nobody should
later read "Phill accepted (a)" as "Phill declined (b)" or as "Phill approved amending Control 3".
Those are three different decisions and only the first has been made.

### 9.4.2 REMEDIATION — credential broker on the host

Satisfies the original §9.4 constraint — *a credential that opens nothing else* — **without amending
Control 3 and without introducing spend.** Written now so option (b) does not become the default
merely by being the only alternative on paper.

**Shape.** The host keeps `auth.json`. The container never receives it.

```
container  ──HTTP──▶  broker (host, loopback-scoped)  ──HTTPS──▶  model endpoint
   no credential          holds auth.json, injects it        authenticated
```

**Properties required of the broker.** Each is a design constraint, not a nicety:

1. **It is a proxy, not a vending machine.** It injects the credential into a forwarded request. It
   never returns the credential, on any path, under any error condition. A broker that hands the
   token to the container on request is the mounted file with extra steps.
2. **Destination-locked.** It forwards only to the model endpoint, only the paths the reviewer needs,
   and refuses everything else. An unconstrained forwarder is an open proxy that grants *more* than
   the mounted credential did — a remediation that increases blast radius is a regression.
3. **Reachable only by the container.** Bound to the container gateway interface, never `0.0.0.0`.
4. **Auditable.** Every forwarded request is logged host-side, so the reviewer's model traffic becomes
   observable — which the current arrangement does not provide.

**Then `auth.json` leaves the mount list entirely**, and §9.3's disclosure list drops to: the repo,
the brief, and the transcript.

**Feasibility unknown, stated rather than assumed.** This requires the Codex CLI to accept a
non-default base URL or an HTTP proxy for model traffic. **I have not verified that it does**, and I
am not going to describe its configuration surface from documentation — that is the §2 mistake. If
the CLI cannot be pointed at a broker, this remediation does not work and the ruling's remediation
field is unsatisfiable; that finding should reopen §9.4 rather than quietly persist. **Verify before
scheduling the build.**

## 9.5 Proving the mount boundary — red first, two arms

Same shape as §9.0: **the same probe, inside and outside.** The outside arm is what makes an inside
refusal evidence rather than a broken probe.

**Expected INSIDE the container:**

| check | required result | boundary being proven |
|---|---|---|
| `READ_CREDENTIAL[.railway/config.json]` | **FAIL ENOENT** | host `~` not in namespace |
| `READ_CREDENTIAL[.ssh/id_ed25519]` | **FAIL ENOENT** | no key material |
| `READ_OUTSIDE_TREE` (`~/.gitconfig`) | **FAIL ENOENT** | host home absent |
| `WRITE_OUTSIDE_TREE` | **FAIL EROFS/EACCES/ENOENT** | nothing writable outside the tree |
| `SIBLING_REPOS_VISIBLE` | **FAIL or 0** | one repo, not 58 |
| write to tracked source under `/work` | **FAIL EROFS** | read-only source (new check) |
| `SPAWN_NET_USE` / `SPAWN_CMD` | **OK** | §3 execution preserved |
| `WRITE_IN_TREE` / `UNLINK_IN_TREE` (`.next`) | **OK** | build can run |
| `NETWORK` to model + fonts | **OK** | §9.1 |

**The rule you set — a check that cannot fail inside is not evidence — needs its own arm.** A
`FAIL ENOENT` is ambiguous between *the mount excluded it* and *the probe looked in the wrong place*.
So each denial gets a paired positive inside the container:

- **Read:** a decoy file is mounted read-only at a known in-container path with a unique token. The
  probe must **read the decoy successfully** and **fail on the host paths in the same run.** Same
  mechanism, same process, only the path differs — the §6 two-arm shape applied within one arm.
- **Write:** the probe must **write successfully to `/work/dashboard/.next`** and **fail outside the
  tree in the same run.**

Both denials without their paired success are **not evidence** and the run must be treated as
unproven. A probe that reports six `ENOENT`s and never demonstrated a successful read has measured
nothing.

**Gate:** this proof runs **before the first real review**, and its result is recorded. If any denial
lacks its paired success, the container is not accepted.

### 9.5.1 RESULT — executed 2026-08-03: **PASS**

Probe: `.harness/sandbox-probe/mount-proof.cjs`. Two arms, same probe, same run shape.
Container: stock `node:22-slim` (`sha256:f32b8106…`) — **no custom image built**; the mount boundary
is a property of the mount configuration, not of image contents.

Mounts under test: `D:\Pi-Dev-Ops → /work:ro`, decoy dir `→ /decoy:ro`, `tmpfs → /work/dashboard/.next`.
Nothing else.

| check | ARM OUTSIDE (host) | ARM INSIDE (container) | required | verdict |
|---|---|---|---|---|
| `~/.ssh/id_ed25519` | REACHABLE 387 B | **ENOENT** | deny | ✅ |
| `~/.railway/config.json` | REACHABLE 747 B | **ENOENT** | deny | ✅ |
| `~/.codex/auth.json` | REACHABLE 4558 B | **ENOENT** | deny | ✅ |
| `~/.gitconfig` | REACHABLE 636 B | **ENOENT** | deny | ✅ |
| `/host_mnt/c`, `/mnt/c`, `/c`, `/run/desktop` | `/c` REACHABLE | **all ENOENT** | deny | ✅ |
| sibling repos | **58** | **0** | deny | ✅ |
| write tracked source | WRITABLE | **EROFS** | deny | ✅ |
| **READ_POSITIVE (decoy)** | OK | **OK, 33 B** | succeed | ✅ |
| **WRITE_POSITIVE (`.next`)** | OK | **OK, write+unlink verified** | succeed | ✅ |
| read `/work` | OK 79 entries | **OK 80 entries** | succeed | ✅ |
| `SPAWN` (§3) | OK | **OK** | succeed | ✅ |
| `NETWORK_EGRESS` (§9.1) | OK | **OK** | succeed | ✅ |

**Both paired positives passed, so every denial is evidence rather than an ambiguous `ENOENT`.**

**The strongest single result is `EROFS`, not `ENOENT`, on the source write.** The file is present and
readable (`READ_TREE` OK, 80 entries) and the write was refused *by the mount mode*. That denial is
attributable to read-only-ness itself — it cannot be explained by the probe looking in the wrong
place, which is the failure §9.5 was designed to exclude.

**Measured mount table — the manifest baseline for the Control 1b successor (§9.6):**

```
/work                     9p     ro   (path=D:\)
/decoy                    9p     ro   (path=C:\)
/work/dashboard/.next     tmpfs  rw   nosuid,nodev,noexec,mode=777
```

Exactly three mounts, two read-only. This is the declared set the pre-run assertion compares against.

### 9.5.2 What this does NOT prove — residuals

1. **The loop has not been run in the container.** This proves the **boundary**, not that the review
   loop executes inside it. `node_modules` was not mounted and no build ran. §9.2's writable-set
   measurement and the Supabase question are still open and are the natural next step.
2. **Symlink traversal is UNTESTED.** The 9p mount options include `symlinkroot=/mnt/host/`, which is
   a plausible escape route. Partial evidence only: `/mnt` is empty, `/mnt/host` **does not exist**,
   and `/work/..` resolves to the *container* root (`bin boot dev etc home`), not `D:\`. But I did
   **not** test an actual symlink — creating one on this host requires Administrator privilege and
   the attempt was refused. **A repo containing a symlink pointing outside the tree remains an
   untested vector.** Test it before the first real review, from an elevated shell.
3. **Stock image, not the review image.** `node:22-slim` has no toolchain pinning, so this says
   nothing about Control 4 (§9.6.1), which is unimplemented.
4. **`.next` was tmpfs, not the specified volume.** Adequate for proving writability; the real
   configuration may differ in persistence semantics between rounds.
5. **Not a privilege-escalation audit.** Default `runc` + builtin seccomp; container-escape classes
   (kernel exploits, misconfigured caps) were not assessed and are out of scope here.

## 9.6 What happens to the controls

| control | under the container |
|---|---|
| **1 — tree integrity** (`:52-68`, `:113-150`) | **Retained, and partly superseded.** Read-only source makes a source write *impossible* rather than *detected*; the hash still covers the writable overlays and still catches the builder committing mid-review, which is operator error and unrelated to isolation. Keep it. Its documented blindness to gitignored paths (`:57-61`) is unchanged and still correct. |
| **1b — codex config hash** (`:70-94`, `:152-160`) | **Becomes unnecessary in its current form, and is REPLACED, not simply deleted.** `~/.codex/config.toml` is not mounted, so self-escalation through it is structurally impossible rather than detected. **Successor control: a mount-manifest assertion** — before each run, compare the container's actual mount table against the declared manifest in §9.3 and **fail closed on any extra, any missing, or any read-only mount that is writable.** That is the same fail-closed-on-the-unrecognised property `:85-87` was built for, aimed at the thing that now carries the boundary. **Do not retire 1b until §9.5 passes.** Retiring a control on the assumption of a boundary, before the boundary is proven, is the exact error this document exists to prevent. |
| **2 — execution proof** (`:162-175`) | **UNAFFECTED. Confirmed.** Isolation and execution are orthogonal axes. The container changes where the suite runs, not whether the transcript shows it ran. The grep for `Tests N passed` / `Test Files N` is unchanged, and §3 keeps it non-negotiable: a reviewer that cannot execute cannot validate a verifier. If anything it gains weight — a fresh container is *more* likely to fail to execute for environmental reasons, and this is the control that makes that loud rather than silent. |
| **3 — plan auth** (`:42-49`) | **Unchanged.** §9.4.1 ruled option (a), so Control 3 stands as written. It is a spend-posture control and is explicitly out of scope for this isolation work (§9.4.1). |
| **4 — image identity** (NEW) | **See §9.6.1.** Covers image drift, which none of 1, 1b, 2 or 3 covers. |

### 9.6.1 Control 4 — image identity, pinned by digest

**The gap.** The container's image pins a toolchain that can diverge from the repo's. A rebuilt or
retagged image changes what the suite runs on while every existing control stays green: Control 1
hashes the tree, 1b/its successor covers mounts, Control 2 only asks whether a suite ran. **A review
can be fully evidenced and still have run on the wrong toolchain.** Nothing currently detects it.

**The control.** Same shape as the config hash it is modelled on (`codex-review.sh:88-93`):

1. **Pin by digest, never by tag.** `image@sha256:<digest>` recorded in a committed manifest.
   A tag is a mutable pointer; pinning to one is pinning to nothing.
2. **Assert before every run.** Resolve the digest of the image actually about to be used and compare
   it to the manifest. **Fail closed on any digest not in the manifest** — unrecognised is a failure,
   not a warning. This inherits 1b's deliberate posture (`:85-87`): exclude known churn, fail closed
   on everything unrecognised, so a new or unexpected image trips it rather than sliding through.
3. **Bind the digest to the evidence.** Record it in the transcript alongside HEAD, so a report is
   bound to *the image that produced it* the way it is already bound to the commit. A finding whose
   toolchain is unknown is not reproducible.
4. **Rotation is an explicit, reviewed act.** Updating the pin is a commit to the manifest with a
   reason. That is the whole point — drift becomes a diff instead of an accident.

**Red-first proof.** The control must be shown to fail before it is trusted: point the runner at a
rebuilt or otherwise different image and confirm the run **refuses**. A pin that has never rejected
anything is a string in a file. Pair it with the positive arm — the manifest digest runs clean — so a
refusal is attributable to the digest and not to a broken runner.

**Known limit, stated.** This binds the image, not its contents' provenance. It proves *the same
image as last time*, not *an image built from trusted inputs*. Supply-chain assurance for the image
build is a separate problem and is not claimed here.

## 9.7 Open items before build

1. **Container runtime — MEASURED 2026-08-03. Installed, not running.** This is materially different
   from absent: nothing needs procuring, something needs starting.

   | component | state |
   |---|---|
   | Docker CLI | **present** — `C:\Program Files\Docker\Docker\resources\bin\docker` |
   | Docker daemon | **unreachable** — `npipe:////./pipe/dockerDesktopLinuxEngine` does not exist |
   | Docker Desktop process | **not running** |
   | WSL | **present**, default version 2, default distro `Ubuntu` |
   | WSL distros | `Ubuntu` (Stopped), `docker-desktop` (Stopped) |
   | podman / nerdctl / containerd | absent |

   The `docker-desktop` WSL distro exists, which is Docker Desktop's Linux engine backing — so the
   engine was provisioned, just stopped.

   **RESOLVED 2026-08-03 — started on instruction, daemon proven up in ~8s:**

   | field | value |
   |---|---|
   | Client / Server | **29.6.2 / 29.6.2** |
   | OSType / Arch | **linux/x86_64** |
   | Storage driver | `overlayfs` |
   | Cgroup | `cgroupfs` **v2** |
   | Kernel | `6.6.87.2-microsoft-standard-WSL2` |
   | CPUs / Memory | 8 / ~7.8 GB |
   | Runtime / security | `runc`; `seccomp=builtin`, `cgroupns` |

   **A Linux engine is what §9.3 assumed** — read-only bind mounts, mount namespaces and per-mount
   modes all behave as specified, rather than the Windows-container semantics that would have
   required a different design. cgroup v2 and a stock seccomp profile are present.

   Three things this does **not** yet prove, kept explicit:

   - **Not that the mounts behave as specified.** Runtime up ≠ boundary real. §9.5 is still the only
     thing that establishes that, and it has not been run.
   - **Not persistence.** This was a manual start of a desktop application. Whether the daemon
     survives a reboot depends on Docker Desktop's auto-start setting, which is **unchecked**. A
     review runner that assumes a running daemon needs to fail loudly when it is absent, not hang.
   - **Not performance.** The repo lives on `D:` (NTFS) and will be bind-mounted into a WSL2 Linux
     VM, so every build crosses the 9p/virtiofs translation layer. §5 flagged this as materially
     slower; it remains **unmeasured**, and it is the tradeoff most likely to be felt per round.

2. **The writable set** (§9.3) — measure the `EACCES` paths, do not predict them.
3. **Supabase egress** (§9.2) — resolves on first containerised run with a clean DNS cache.
4. ~~§9.4 ruling~~ — **RULED 2026-08-03: option (a)**, recorded as accepted exposure with the
   credential broker (§9.4.2) as populated remediation. See §9.4.1.
5. ~~Image drift~~ — **SPECIFIED: Control 4** (§9.6.1), pinned by digest, fail-closed on unrecognised.
6. **Broker feasibility** (§9.4.2) — verify the Codex CLI accepts a non-default base URL or HTTP
   proxy for model traffic. **Unverified.** If it does not, the ruling's remediation is unsatisfiable
   and §9.4 reopens.
