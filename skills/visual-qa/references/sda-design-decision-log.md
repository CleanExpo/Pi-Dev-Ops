# SDA commercial visual acceptance: system decision, 31 October 2026

**Reason:** technical browser, build and CI checks can pass while a user-facing
film or interface remains visually poor, has overlapping typography, contains
unapproved assets or lacks commercial delivery evidence.

**Reuse the existing stack:** `visual-qa`, `design-board`, `design-approve`,
Playwright, frozen accepted variants, SPM and JEV. Do not create another
orchestrator or repeat finished design work without new evidence.

## Fixed release contract

- Actual Chromium screenshots at mobile 390x844, tablet 768x1024 and
  desktop 1440x900, with the relevant visible images decoded and errors logged.
- For moving media, inspect genuine source/master frames at time-coded
  transitions. Screenshots and hashes alone are not a creative judgement.
- Preserve exact accepted prior baseline hash. New screenshots do not silently
  become a new approved baseline.
- Use 100-point rubric in `skills/visual-qa/references/sda-commercial-acceptance.md`.
  Two genuinely performed critiques, SDA and an independent challenger,
  must score >=85 overall with no area below half.
- Rights, truthful claims, authentic approved script/voice/music where relevant,
  complete playback, caption alignment, and exact-version founder/customer
  acceptance are distinct gates. Output remains REVIEW/HOLD without these.
- Maximum three targeted iterations, then change design direction. Do not
  replace original accepted assets with placeholders or scratch audio.
- No external push, merge, public publication, paid API use, deletion or
  production deployment without its own approval.

## Technical enforcement boundaries

`skills/visual-qa/scripts/sda_evidence_gate.py` fail-closes evidence
completeness, hashes and declared review records in `--release` mode.
It **does not** identify reviewers, authenticate approvals, assess artistic
quality or supply a commercial rights licence. Those must be validated through
actual review and source receipts. The `UserPromptSubmit` route is a routing
hint, not a hard runtime security boundary.

`scripts/install-sda-visual-hook.py` is opt-in and preserves existing hooks.
Do not run a global installer merely because a PR passed CI. Review the
canonical skill-library change first; then install on each authorised machine.

## Motivating, verified examples

- Synthex #1088 had stranded local fixes and generic green CI checks that did
  not run its Python card builder; a separate feature-specific acceptance
  suite was required.
- The 31 October private V3B Business Card film visibly double-exposed text
  at 15.40s even though earlier technical video checks passed.
- Existing Run14/Run15 Playwright screenshots were technically clean after
  targeted corrections; neither run establishes professional creative
  acceptance or finished customer delivery.

Track system improvements in Linear RA-6473 and commercial card delivery in
UNI-3027/UNI-3000. This document is code-repository memory for future
sessions and agents; it is not an approval receipt.


## Independent fail-first review and remediation (31 October)

Codex independent exact-SHA review of initial candidate f6de5e60 returned
**FAIL, five P1 findings**: browser-health fields treated as optional,
arbitrary bytes accepted as PNGs, NaN bypassed scoring, fake baseline
digests were accepted, and interrupted hook install could truncate existing
security settings. The revised branch now requires real PNG decode/viewport
measurements, rejects non-finite scores, binds comparison to separately
frozen baseline approval, and atomically writes hook settings. Focused
regression tests cover all five; any future reviewer still must run and
record their own independent review at the revised final commit.

## Second independent review, correction cycle 3

Codex's independent review of SHA f7973ddb also returned **FAIL (5 P1)**:
an uncoordinated settings writer could be overwritten by the installer;
the audited JSON could mutate between hash and later parse;
the candidate could silently shrink its own expected page scope;
path aliases could reuse one physical screenshot as several pages; and
release evidence allowed fake frame/master bytes. The third bounded
repair therefore converted settings installation to atomic create-only
(never overwrites); hashes and parses the same byte snapshot; requires a
separate independently supplied scope record; compares canonical paths;
and validates actual master decoding and exact FFmpeg-extracted frame bytes.
A third exact-SHA independent review is required. If it still fails,
change strategy rather than repeatedly patching this implementation.


## Third independent review, governance-only remaining correction

At exact commit 7d0bf179 the independent Codex reviewer returned **FAIL**
on one P1: ambiguous wording suggested Jev could verify commercial
rights and independent-review signatures. Binding CLAUDE.md states Jev
is advisory-only. The subsequent change removes that authority and
requires checks against authorised human/source-of-truth records.
This is a narrowly scoped documentation correction; it does not invent
a JEV run, licence, founder approval or release acceptance. A new exact
SHA independent review and receipt still bind any release.


## Fourth independent review: actual symlink-swap finding

An exact-head Codex independent review of `750aadfe` returned **FAIL**
for a genuine O_NOFOLLOW missing check. It reproduced a path replacement
to an external symlink after containment but before the evidence read.
The revised candidate opens file components relative to trusted held
directory descriptors with O_NOFOLLOW and verifies the bytes read from
that same handle. A targeted adversarial regression exercises the
reported race; release remains HOLD until a fresh exact-head
independent reviewer and the repository's authenticated PR gate pass.


## Consolidation mandate, 31 October: work must land in main safely

The founder directed merging reviewed work, retiring merged/obsolete
branches, and requiring full visual/audio sync testing rather than more
preview cycles. Confirmed Synthex PR #1088 and #1086 were both merged into
GitHub main. Their clean feature worktrees (two ~2.1 GiB dependencies
copies) and local merged branch refs were safely removed after exact
commit-ancestry verification. Other dirty or uniquely committed branches
are preserved pending individually verified release gates.
SDA release verifier adds actual audio/video timing and captions checks,
but it does not authorise unreviewed media, guessed JEV approval,
force pushes or bypass of the exact-SHA PR release receipt.

## 31 October 2026: isolated SDA observer evidence review

A clean isolated branch from locally reviewed security source d09e5440
preserves the dirty feature worktree and dirty Pi-Dev-Ops root.

Red-first negative controls found that duplicate copied/hardlinked screenshot
bytes were counted as separate mobile/tablet views; wrong PNG geometry and
non-PNG arbitrary bytes were promoted as browser evidence. Worse, the original
viewer test reported 50/50 PASS while writing through symlinked output files
and overwriting a synthetic outside canary. The copied unguarded observer lock
also timed out on a hardlink control. No user data was used in these probes.

New controls: O_NOFOLLOW held descriptor for screenshot bytes, unique inode
and SHA, real PNG IHDR viewport geometry, source HTML digest, required empty
network/block/error fields, time-bounded evidence and a protected observer
PID file. The client/expert viewer's own screenshot/receipt writer now uses
private directory checks plus exclusive atomic writes. It cannot approve a
release or falsely label static screenshots as a live stream.

MacBook tests: 7 security + 17 observer provenance + 52 actual Chrome
mobile/tablet/desktop + 37 media/evidence tests passed. Mac Mini repeated
17 provenance tests from matching SHA256 source. Local canonical skill
portability 119 PASS; GitHub API for pinned owner 373e65ad returned 404,
so remote availability is NOT verified. The private Business Card media
has 60 s video and 60 s AAC audio with 0 ms end drift but no verified
subtitles or media rights. Claude/JEV were NOT run on this candidate.

The SHA256 evidence and source receipt is stored in
skills-library/sda-localhost-review-prototype/GUARDIAN_PROVENANCE_20261031.json.
Remain RELEASE HOLD: exact-head independent code review, remote source
authority, signed PR gate, tenant authentication, dynamic interaction and
commercial/rights approvals all remain outside the scope of this patch.

## 31 October 09:35 AEST: Codex P1 source validation found and red-first repaired

Independent OpenAI Codex read-only review of exact SHA bdb6ae91 returned
P0 none, **P1 FAIL** because PNG viewer validation inspected only 24
header bytes. It also recorded two P2s: per-screenshot freshness and
user-editable test_results.json could overclaim authority, while localhost
runtime used an older observer source than the reviewed commit. Separate
Claude CLI review failed due autocompact thrashing, NOT a PASS. No JEV run.

Red-first regression reproduced the actual P1: a correctly formatted PNG
signature+IHDR+IEND, with valid declared width/height but no pixel data,
was wrongly promoted as browser screenshot evidence. New validator parses
the entire PNG, verifies chunk CRCs, bounded IDAT zlib decompression,
expected decoded byte count and scanline filter codes. It accepts only
supported non-interlaced 8-bit RGB/RGBA, rejects unknown critical chunks,
trailing data and invalid dimensions; no Pillow/ffmpeg required. Red-first
single-shot stale timestamps and fabricated exact-SHA test pass counts
also reproduced and were fixed. Unsigned local test counts are expressly
NOT trusted release authority.

29/29 combined security/provenance MacBook Python tests and 22/22 Mini
Python 3.14 tests PASS; 3/3 actual Chrome captures passed full PNG decode
and remain Release HOLD. New exact-head independent review required.
Existing localhost observer was still running the older source when
original review occurred; do not claim it is running the new verifier
until a guarded replace/restart and producer SHA check passes.

Source/test and review receipt: skills-library/sda-localhost-review-prototype/
GUARDIAN_PNG_REPAIR_20261031.json, SHA256-recorded local logs. No push,
merge, external deployment or commercial authorisation.


## 31 October 12:27 AEST: full client interaction smoke, not just screenshots

The new SDA JavaScript-enabled browser contract lives on the separate,
clean `feat/sda-interactive-browser-contract-20261031` worktree, based on
`d0834587`. It runs an actual Chrome client/expert/keyboard journey at
390/768/1440 px through the already authorised loopback viewer.
It checks screenshot pixels decode at the correct dimensions, and
independently hashes the image bytes delivered by the browser to prevent
a 1×1 substitute or screenshot-serving drift from appearing verified.
It checks page errors, unexpected requests and correct SNAPSHOT/HOLD labels.

Initial positive fixture **72/72 PASS**. Synthetic broken-image (HTTP 404)
was **injected 3 actual times**, forced the probe's exit code to **1**,
and was detected by five separate controls; the combined
`run_interactive_contract.sh` only returned 0 after checking this.
Receipts, exact replay command and hashes:
`skills-library/sda-localhost-review-prototype/INTERACTIVE_CONTRACT_20261031.md`.
A separate source-only commit and exact SHA review are still required;
do not treat pre-commit test evidence as approval of a later revision.

Client approval remains disabled; canonical remote pin, signed exact-head
CI, real dynamic client site acceptance, commercial rights, audio/caption
approval and full three-host parity remain Release HOLD. No JEV run was
performed. The dirty SDA and Pi-Dev-Ops worktrees were not edited.

## 31 October 12:35 AEST: independent P1 challenges, guarded remediation

First exact-commit `7962b713` read-only reviewers did **NOT**
approve: OpenAI Codex found two P1s (popup first request outside
page-only route; second screenshot fetch verified different bytes).
Claude Sonnet independently found P1s in source binding, untested
routing controls and overclaimed evidence labels. Explicit dissent
is preserved in /tmp/sda-interactive-{codex,claude}-exact-7962b713*;
JEV was not called. No model verdict grants release authority.

Corrections in a separate clean-branch working copy: context-level
origin guard installed before page creation; hash actually delivered
screenshot responses; independently cross-check observer checkout Git
SHA; refuse dirty source and mismatched two-phase receipts; change
self-reported freshness labels to actual claim wording; add synthetic
loopback popup, WebSocket and first-party 302 canaries in addition
to broken-image injection. Initial development test: 75/75 normal
checks, expected red 76/81 negative, 1 popup + 1 WebSocket + 1 redirect
blocked and zero canary hits; run again after commit and independent
code challenge before merging or claiming acceptance. Media, rights,
remote canonical source publication and authenticated approvals remain
HOLD; current dirty original feature checkout was untouched.

## Third bounded correction: fail-closed Git status and Chrome launch

Independent Codex review of exact SHA `27c7f6e1` returned **P1 FAIL**
for a genuine synthetic `git status --porcelain` command failure:
the shell used an output-only conditional, silently ignoring exit 128
when stdout was empty. A real red-first fixture reproduced exit 0.
The revised wrapper requires the Git status command to EXIT ZERO
**both before and after** the two browser phases, in addition to
requiring an empty status and the same exact SHA. A status error exits 2
with HOLD before it can be called a pass.

The reviewer also identified the possibility that a rejected Chrome
launch could leave the temporary canary server open. The new
`try/finally` closes the local server even when launching Chrome
fails; an intentionally nonexistent Chrome binary returned **exit 1**
with no hang. Reviewer code quality is not automatically transferred
to the new exact SHA: commit this correction, rerun the test bundle and
obtain a new independent verdict. This remains a local, unsigned
non-release acceptance profile.


## SDA fail-closed Chrome shutdown receipt, 31 October 2026 (RA-6473)

**Unpublished isolated code commit:** 76d92abf2dd318e8f6af52213532b66bbea1e100 on feat/sda-browser-close-guard-20261031, descended from independently reviewed 182b0c5262b61f2fc1fcd51e68de656964d5d0b9. Original dirty SDA checkout and Pi-Dev-Ops root were untouched.

**Red-first proof:** The previous source swallowed a real Playwright browser.close() error and returned exit 0 with 75 passing browser checks. The deliberate real-Chrome fault injection test failed red-first as expected (log SHA256 a468460b1b698609ca8899a8c9db3fd50fc3b954fe7b3bc3a5d74cecff38a198). The code now records an explicit Chrome shutdown check in every successful browser run and a failed check upon shutdown rejection, making the probe exit nonzero. The identical injected fault is now correctly rejected (75 otherwise passing browser checks; negative test exit 0), log SHA256 8abffe293a355bf73d9b54bdbc31a543e9cca21f589f6e3c3eb5bf8c5b4d693f.

**Positive and adversarial replay on committed code:** Real mobile 390x844, tablet 768x1024 and desktop 1440x900 Playwright Chrome checks passed 76/76 including the successful browser-close check. The exact-head one-command interactive contract returned exit 0: positive 76/76; deliberately invalid image yielded expected probe exit 1 with 2 real fault requests, 5 detected check failures, one popup blocked, one WebSocket blocked, one redirect blocked and zero canary hits. Source commit exact matched in receipt. Evidence directory /tmp/sda-interactive-proof-t2fmWYKd/contract_summary.json, positive receipt SHA256 cd94190cc2918fc5f13ffcef12a47f8d38c29047c3efd1e2b7bcce7fe879ecd9, negative receipt SHA256 eaf14c8763004eb33d9a79fd37f1b25de03a54b26c8fe7ec615e17cb76525ea6. Combined contract log SHA256 20d8164188e71ec7e273c57326d4dde930ec413963b6983d719ae81378086fda.

**Three-host syntax and content, not full browser parity:** The new probe SHA256 65327497b8b82ff8b2c7c739db33f42b203757d0d0511ddca93535fa7c058655 matched on MacBook, Mac Mini via Tailscale SSH stdin (no writes), and Windows PC (temporary source copy deleted). Node syntax checks exited 0 on each. This is not CI or complete cross-host visual replay.

**Remaining governance:** At recording, exact-SHA independent Claude/Codex reviews were launched; findings are not yet incorporated here. JEV not run. Browser evidence, UI snapshot and code checks are not a licence, independent signed PR receipt or authenticated client approval. Pi-Dev-Ops canonical published-pin mismatch, dirty original observer worktree, tenant identity/authority and full live dynamic client session remain open. No push, PR, merge, deploy, client action or paid API made here. **Release HOLD.** Next: evaluate independent reviewer dissent, reconcile authoritative upstream skill in isolated worktree and governed PR, then exact-head CI and authenticated end-to-end website session.


### Independent review disposition and canonical pin, 31 October 2026 (follow-up)

Real Claude Sonnet source-only review of exact code commit 76d92abf2dd318e8f6af52213532b66bbea1e100 returned **no P0/P1 in its narrow source reading**, explicitly *not* CI or a replay of tests. It identified P2 follow-ups: bound Chrome-close timeout; use an exact required check list rather than only >=75; synthetic rejection after real close does not simulate a genuinely leaked Chrome process; harden diagnostic receipt for other finally-block failures. Claude actual output /tmp/sda-close-review-claude-76d92abf.json. The model did not authenticate screenshot provenance or rights.

OpenAI Codex exact-code independent review of 76d92abf was attempted, but the CLI experienced HTTP 403/WebSocket connection failures and an invalid thread-store/collaboration failure, and **returned no final verdict**. Our single stalled reviewer process was terminated after the bounded attempt. Do not fabricate a Codex PASS, or apply the earlier 182b0c52 review to this code. JEV not run. Any required independent model review still needs a clean authenticated retry through the proper reviewing service and signed exact-head gate.

Authenticated read-only GitHub REST fetch on 31 October returned **HTTP 422 / No commit found** for canonical Pi-Dev-Ops pinned commit 09e63e79bf33a7d6688b0a9e1fbe1f14e1baaf68. The unpublished pin and downstream source-of-truth are still a hard release HOLD; do not upgrade a private local object to 'published'. The code and evidence branch HEAD after test-data commits is b426af4cda8bfd6085cadb7a54dbf1a61de7c750, still not pushed and originally dirty observer untouched. Next: publish and pin canonical owner through approved PR, complete clean CI, add a bounded Chrome-close timeout if warranted, then a real authenticated client session; do not merge/deploy or approve on model-only evidence.

## SDA Chrome-close bounded teardown · 2026-10-31 13:25 AEST · RA-6473

- **Scope:** isolated worktree `/private/tmp/sda-browser-close-timeout-20261031`, branch `feat/sda-browser-close-timeout-20261031`; code/test commit **`13272edc46df82f67ce719d680fe992e257495b3`**. Original SDA feature checkout at `91ef0ff3` dirty, left untouched; Pi-Dev-Ops root dirty, untouched. No push, PR merge, deploy, published asset, spending or bypass.
- **Failing red-first fact:** existing probe could run 75+ real Chrome checks and then hang forever if `browser.close()` never settled. Test-only Playwright stub runs actual `close()` and deliberately leaves returned promise unresolved. Prior probe failed to write a receipt and required the outer harness's 55-second limit; `negativeControlPassed=false`. Raw log SHA256 `9ed7c3e04a4150adae0081981ea8b71c349adbdc23bd0c79003fe92b849591f7`.
- **Repair:** bounded 10,000 ms Playwright shutdown using `Promise.race`, explicit failed shutdown check, synchronously recorded receipt and nonzero exit even when an injected promise leaves a timer running. This is a local *fail-closed* verification improvement, not proof all Chrome processes are reaped after a genuine underlying browser hang.
- **Fixed injected negative:** harness exited zero as a successful *negative-control test*; underlying probe exit **1**; explicit failed check `Chrome shutdown completed cleanly`, `Error: Chrome shutdown timed out after 10000ms`; **75 of 76** other real-browser checks passed; receipt present and captured. Log SHA256 `620e72676a8114ff5ee0dee44c2ea8fb10ec533574775527fc0588097b2a6f5b`.
- **Exact-code positive/negative browser contract:** `bash skills-library/sda-localhost-review-prototype/run_interactive_contract.sh` on code SHA `13272edc` returned **exit 0**. Positive Chrome mobile (390×844), tablet (768×1024), desktop (1440×900): **76/76 pass**; deliberate invalid image negative probe **exit 1**, **5 targeted failing checks**, 2 actual image injection requests, popup/WebSocket/redirect requests intercepted with zero canary hits. Source SHA and observer SHA matched in receipts; artifacts byte-hashed. Contract-summary SHA256 `14f1e04f25b5626169c02229962f5aed3419c8bf92d469a9d51458cde642039e`. Full temporary screenshots stay in `/tmp/sda-interactive-proof-4YOUlOYh`.
- **Two-host source portability:** exact `probe_interactive.cjs` SHA256 `8a3ceae45c8e645fe4abd0681cdaa0cb73acc3d24b14488764a340362a56345a`; `node --check` **passed MacBook and SSH-connected Mac Mini** with matching stdin hashes, no Mini disk writes. Windows not checked for this new patch; cross-host *browser replay* and authentic independent CI not yet proven.
- **Actual media streams (fresh FFprobe):** RestoreAssist review MP4 has 60.000-second H.264 video and **no audio stream**; Business Card candidate has 60.000-second H.264 video and 60.000-second AAC audio, **0.0 ms stream-end drift**. Neither has verified narration captions, creative/media rights or authenticated film approval. **Both remain HOLD.**
- **Source and approval gate:** GitHub `CleanExpo/Pi-Dev-Ops` exact canonical commit `09e63e79bf33a7d6688b0a9e1fbe1f14e1baaf68` still read as **HTTP 404 Not Found** at this checkpoint. No confirmed canonical publication, signed exact-head PR CI, tenant-scoped authenticated client approvals, rights clearance or completed end-to-end client workflow. Viewer HTTP 200 with actual snapshot, not streaming. **RELEASE HOLD**.
- **Independent review:** actual Claude Sonnet read-only exact-source review launched for `13272edc`; final signed verdict **not presumed**. No fresh Codex verdict or JEV run in this repair. Existing upstream review cannot be reused for this SHA.
- **Evidence:** `skills-library/sda-localhost-review-prototype/evidence/20261031_close_timeout/` contains red-first/fixed negative logs, exact Chrome contract receipt pair, manifest with SHA256 for each file, and fresh FFprobe stream evidence. Keep unmodified canonical source and current release HOLD until signed checks clear.
- **Next:** obtain/record the independent exact-code review; exercise hung-close real-browser cleanup without fabricating success; prove Chrome browser replay on Windows and Mini where installed; resolve canonical Pi-Dev-Ops publication through a governed PR; then build an authenticated client session and improve mobile first-fold comprehension.

### Independent advisory review addendum · 2026-10-31 13:29 AEST

Claude Sonnet read-only source review **completed** (not a test run, security attestation or release authority). Reported **no P0**, **conditional P1**: if an actual Chrome `close()` hangs *before closing the underlying process*, forced Node exit could orphan Chrome; test currently closes real Chrome before holding the returned promise. Additional **conditional P1**: per-context `context.close()` and redirect/server teardown are not bounded by the new browser-close deadline. P2: fixed 10-second timer/55-second test horizon, magic `>=75` check floor, loose error substring matching. No Codex or JEV review was performed for this new code. **No independent PASS** and RELEASE HOLD.

Claude initially said it could not verify exact code SHA because the branch HEAD had advanced with evidence-only commits. Operator subsequently verified exact **Git blob identity** for both reviewed source files versus code SHA `13272edc`: probe object `fa2ec79770591890daca6772a7c4265d0dd38dfb`, test object `c8b3790bc823b9845fa3b2c7e00dcca70a47996e`, both matching working files. This proves source-byte parity only, **not** a reviewer-authenticated Git diff or a signed independent release review. Complete reviewer text and hashes preserved in the source evidence directory.

**Next independent test:** ensure an outer OS process-group watchdog terminates the *actual launched Chrome child process* when `browser.close()` or `context.close()` never settles, and demands a nonzero result with a durable explicit HOLD. Verify Chrome PID is gone afterward, no false-green, plus repeat positive Chrome/negative browser probes before treating the P1 as resolved. Keep the original dirty checkouts and remote publishing untouched.

## RA-6473 mobile first-fold visibility (31 October 2026)

Reversible local prototype only. The 390 x 844 Playwright Chrome
baseline showed the first detailed progress row at y=2205px,
far below the phone's initial visible area. Added a compact read-only
status card that renders the first outstanding step from the existing
observer state and never displays an Approved claim. The card now
occupies y=355-464px on 390 x 844; the rest of the progress history
remains further down the page.

A separate clean worktree preserves dirty source checkouts. The
baseline failed the new first-fold test (missing summary, expected
RED), then 4/4 real Playwright Chrome contracts PASS on phone,
tablet, desktop and deliberately disconnected observer. The offline
test must show DISCONNECTED and keep release HOLD. Zero JS page
errors and zero horizontal overflow across the three Chrome viewports.
This control does not add sign-in, live streaming or approval authority.

The local media probe inspected actual H.264/AAC tracks: the private
60s Business Card candidate has zero measured start/end drift; the
RestoreAssist 60s and 5s reveal sources are visual-only. No SRT
files were located in the selected local visual-lane tree; captions
and licensing remain unverified. Source evidence is inventoried by
SHA-256 under the prototype evidence/20261031_mobile_firstfold
directory. Screenshot PNGs remain on the MacBook in
/tmp/sda-mobile-evidence-20261031 with committed SHA-256 checksums,
not the binaries, avoiding repository media bloat.

Release: HOLD. This is not independent Claude/OpenAI/JEV release
approval or a signed PR receipt. Pending the unpublished canonical
Pi-Dev-Ops pin, Chrome process cleanup controls, authenticated client
permissions, independently accepted media/captions and exact-SHA CI,
the browser preview must remain local and read-only.

### RA-6473 correction cycle 2: independent Codex challenge on 3083ded6

A real read-only OpenAI Codex reviewer inspected exact local Git
SHA 3083ded6 and returned FAIL, zero P0, one P1 (the browser test
could pass without verifying the actually served candidate HTML,
current observer SHA or fresh progress). It also found P2 reconnect
false-green, missing phone preview disclaimer and incomplete evidence
portability. Review text is preserved byte-for-byte in the private
mobile-firstfold evidence directory. JEV was NOT run and no reviewer
signature or founder approval was issued.

Corrections in a separate clean worktree, without touching the dirty
base: the Playwright test must now match the source file SHA256 to the
actual HTTP HTML bytes, independently bind the observer's exact 40-hex
Git SHA, verify status is fresh and contains a real pending step, and
reject a wrong-staged HTML, stale status and disconnected status. A
device toggle cannot resurrect a cached online badge. The local-only
refresh worker now emits full SHA rather than an ambiguous 8-character
prefix. The phone preview-only disclosure remains visible; a 320x700
small-phone regression was added. Repeated poll updates avoid repeating
unchanged screen-reader text.

The first revised test run with an actual full-SHA observer fixture
was RED because the phone disclaimer was hidden. The corrected local
Chrome run returned 6/6 PASS on phone (390x844), small phone (320x700),
tablet, desktop, disconnect + device toggle, and stale observer
injection. 22 refresh tests, seven capture-security tests and 37
evidence-gate tests passed locally. The existing 76-check interactive
contract passed earlier against SHA 3083ded6; it MUST be rerun after
the final source commit before claiming exact-head Chrome parity.

The added shell contract makes all six Chrome checks reproducible as
a single one-shot, clean-SHA, local-only replay. It creates its own
private temporary directory and no external action or approval. An
observer's unsigned local status is not authenticated tenant evidence,
and the independent review above does NOT clear the revised SHA.
Canonical Pi-Dev-Ops publication, process-level Chrome watchdog,
real client auth, three-machine browser testing, caption/music rights,
JEV and the signed PR release receipt all remain pending. HOLD.

## RA-6473 · 31 October 2026 · SDA process-watchdog third repair

SOURCE exact clean code SHA 10a2bc394c8f2a25f54f45e10190f657683e0b2e
on isolated clean branch feat/sda-process-watchdog-ra6473-20261031,
directory /private/tmp/sda-process-watchdog-guardian-20261031.
Original skills-library 91ef0ff3 working tree and Pi-Dev-Ops root both
DIRTY but PRESERVED. No push, force, merge, deploy or paid API.

Independent source reviews on previous SHA ed304c79 both said HOLD:
Claude 0 P0, 2 P1, 6 P2; Codex 0 P0, 1 P1, 5 P2. Real source reports
are preserved, not signed reviews for the final SHA. JEV NOT run.
Initial 2cc34143 process runner was challenged because detached Chrome
could escape, negative-control failures could hide unexpected shutdown,
and numeric process-group IDs could be reused for unrelated processes.

Third red-first evidence: a mock reused-PGID signal hit an unrelated
group; forged extra HTTP500, empty screenshot arrays, fabricated passing
totals and unexpected Chrome-shutdown failure previously passed the
contract gate. Actual negative stdout preserved under
evidence/20261031_process_watchdog. Correction adds owned-group identity
preflight before killpg; tracks children of known reparented descendants;
defers interruption signals during cleanup; recomputes check totals,
requires exactly three per-mode SHA-bound real screenshots, rejects
unexpected HTTP/console errors, and checks successful Chrome shutdown
in positive AND negative test sessions.

Exact source SHA 10a2bc39 REAL receipts: 76/76 positive Playwright
Chrome checks; deliberately bad image: 5 expected failures, positive
security deny for popup, WebSocket and redirect, 0 canary hits. Watchdog
positive and negative receipts were complete with 0 OBSERVED remaining
workers and 0 unverified inventory, not proof of kernel-level containment.
Private immutable-source artifacts /tmp/sda-interactive-proof-KGI2k35L,
6 real Chrome PNG captures hashed in contract summary. 10/10 synthetic
OS lifecycle controls, 9/9 independent receipt mutation controls and
37/37 visual gate tests PASS on MacBook. Mobile first-fold 6/6 belongs
to previous exact SHA ed304c79, not the current HEAD.

Mac Mini reachable via read-only SSH. Python AST parse and source SHA256
MATCH the MacBook. Mini real Chrome replay and Windows Job Object tests
are NOT established. ffprobe inspected real 60-second Business Card film
with H264/AAC both 60.0s, zero start/end drift, plus 60-second silent
RestoreAssist H264. No externally verified SRT subtitles, voice/music
rights or end-client approval. Technical candidates not commercial masters.

RELEASE HOLD: Chrome worker sampling misses fast double forks before
first poll and a fast orphan can be reported as unverified instead of
proved reaped. Kernel-level stable PID/PGID ownership remains an open
risk. Canonical Pi-Dev-Ops source commit 09e63e79 authenticated GitHub
API returned HTTP404, and signed PR release, full CI/cross-machine Chrome,
per-tenant client authentication, founder/rights approval remain absent.
The safe next strategy after three bounded repair rounds is a stable
browser-process lifetime anchor or kernel-level child supervision, not
another unbounded retry of process sampling. Independent exact-SHA
review of this code is pending and must not be invented.

### RA-6473 · exact-source independent dissent on 10a2bc39 (15:46 AEST)

This is an **actual final independent read-only review**, NOT a signed
approval. Claude Sonnet returned HOLD (0 P0, 2 P1, 8 P2). OpenAI Codex
returned HOLD (0 P0, 1 P1, 2 P2), confirmed exact Git SHA, and used
in-memory counterexamples rather than rerunning live Chrome. Both
identified unsafe residual numeric PID/PGID ownership races, fast escaped
descendants not caught by polling, and incomplete check / PNG provenance.
Claude also identified an interruption window between child Popen and
signal handler setup. Codex demonstrated a forged fixture with internally
consistent hashes and PNG filenames but non-PNG bytes, plus substituted
pass/check labels, which could still be accepted by the in-memory
validator. This is a known **FALSE GREEN RISK** and blocks release.
The raw unedited reviews are at
evidence/20261031_process_watchdog/claude_exact_10a2.json and
evidence/20261031_process_watchdog/codex_exact_10a2.md. JEV NOT run.

No fourth speculative polling patch will be attempted in this bounded
repair session. STRATEGY CHANGE required: stable lifetime-owning
browser-process anchor and/or kernel child monitoring for hard-kill
containment; handlers installed before child spawn; verified independent
PNG decoding and exact named test manifest. Release remains HOLD until
new red-first security cases pass and a new exact-code independent review,
signed PR CI, canonical upstream publish and human rights/signoff
are legitimately completed.

### RA-6473: browser screenshot integrity (31 Oct 2026, ~16:04 AEST)

New isolated branch feat/sda-browser-snapshot-integrity-20261031,
based on 7c11ac0d, code commit eb441a8f622855b65fdfcb7a9461df507eb0dc9e.
Original dirty SDA and Pi-Dev-Ops roots left untouched, no external
change or bypass of signed release governance.

RED FIRST: old viewer displayed alternate valid tablet PNG at the phone
URL and marked it as a phone capture; 7/11 controls passed and 4 failed
as expected. REPAIRED: same-origin no-redirect image fetch, precise byte
length and SHA-256 comparison, same verified response bytes rendered via
blob URL, error removes stale src. Full Chrome evidence: 13/13 focused
real screenshot controls including valid substituted PNG, same-length
altered SHA, missing digest, release HOLD, and 55/55 browser viewer
controls on three viewport sizes with independent stale-HOLD and
fresh-forged-APPROVED negative cases. Test fixtures were frozen from
genuine Chrome captures because another agent updated the live capture
files during the tests; mixing old hashes and new file bytes caused
a reproducible fail-closed error, not an invalid release PASS.

Media: ffprobe verified Business Card candidate 60-second video and
60-second AAC (zero start/end drift); RestoreAssist 60-second H.264
has no audio stream. No approved narration captions or rights proof
were located in this narrow inspection. Local MacBook/Mini JS source
syntax/hash parity only; no three-host browser replay.

Independent exact-head reviews attempted using the connected subscriber
CLIs: neither returned a final verdict within bounded execution. A
partial Codex reading identified that an older forged-approval plus
stale-timestamp test could pass without independently testing staleness.
This was remedied by testing stale valid HOLD and fresh forged APPROVED
separately. No fabricated Claude/Codex/JEV PASS is recorded; JEV
was not called. Previous P1 doubts about process ownership and
canonical Pi-Dev-Ops upstream pin remain unresolved.

RELEASE HOLD: no authenticated tenant approval, licensed assets,
signed PR gate, verified remotely published canonical source, or full
three-host replay. The SHA check verifies local bytes, NOT authorship
or commercial acceptance.

### 31 Oct 2026, 16:33 AEST: historical-image false-green stopped (RA-6473)

- Isolated feature branch: feat/sda-no-unverified-fallback-20261031, code SHA 9d8cde76153e3289bb06e25524b077bdb2c81804. Existing dirty consumer worktree and Pi-Dev-Ops root preserved; no push, merge, deployment, spend or client approval.
- Red-first actual failure: missing/tampered capture.json still exposed historical run21_board PNGs as screenshots in status (2/2 new Python tests failed). The original HTML eagerly fetched a raw unverified desktop screenshot, and the fixed-path allowlist rejected a valid separately scoped localhost page (2/2 additional Chrome negative tests failed; 55/57 checks passed before repair).
- Fix: remove historical fallback enumeration; initial IMG has no source; permit only the exact capture_<viewport>.png in the current same-origin review directory, with no query/hash/user-info. Fetch rejects redirects; SHA-256 verified ArrayBuffer becomes the exact blob displayed. No signed release or livestream claims.
- Green at exact code SHA: MacBook 24/24 observer Python tests, 37/37 visual/media gate tests, 57/57 real Chrome viewer controls across mobile/tablet/desktop including malicious path/query cases, 3/3 real Chrome Run21 captures. Mac Mini over Tailscale SSH: 24/24 observer tests, identical refresh.py SHA256 7c313b786cfc5ac343a2b748957a9d5494f4413f0ca1745fbafe920806ca3b09 and test source bytes.
- Windows honest failure: identical source hashes but Windows 23/24 tests; valid positive fixture was held because os.O_NOFOLLOW does not exist on Windows. This is a genuine cross-platform portability blocker, not a green three-machine result. Require reviewed native Windows no-reparse held-file verification.
- Media ffprobe: actual 60-second Business Card H.264/AAC aligned at 0 ms start/end drift; RestoreAssist 60-second footage has no audio. No SRT files in the two reviewed candidate scopes; no caption or creative-rights clearance.
- Independent review: Claude Sonnet 5.5 provisional diff-only PASS on code SHA with two conditions (blob display and chosen viewport fixed to static UI controls). Both conditions inspected locally; no signed independent release approval. Codex run timed out without a verdict. JEV not run.
- Canonical source: actual vendored Pi-Dev-Ops pin 373e65ad33156deb10fbdb1c2bc33f39f925a7fb exists locally but GitHub REST commit lookup returned HTTP 422; remote provenance and CI acceptance unproven.
- Private candidate preview: http://127.0.0.1:8880/studio_internal/sda_guardian_failclosed_candidate16/ on MacBook, actual Chrome screenshots labelled SNAPSHOT, read-only, no client authentication/approvals. Code/test hashes and logs in skills-library/sda-localhost-review-prototype/evidence/20261031_failclosed_display/. Binary screenshots remain local temporary files, not durable repository blobs. RELEASE HOLD.
- Next: governed upstream source publication, Windows safe-reader parity and cross-host Chrome, protected exact-SHA CI and independent signed review, authenticated tenant-aware approvals, rights/captions, then one genuine website-design session to delivery with receipt.

### RA-6473: Windows native held screenshot reader + honest mobile preview (31 Oct 2026, 17:39 AEST)

- **Isolation and source.** New clean independent worktree /private/tmp/sda-native-windows-held-20261031, feature branch feat/sda-native-windows-held-20261031. Native code SHA a1ba1366aa275c25ec2d277678b389dc944b2052, mobile empty-state code SHA dec72e7ed8b0a96a7616fcfca930af0aaf768aaf. Original dirty SDA checkout and Pi-Dev-Ops root were not changed. No push, PR, merge, deploy, paid API, JEV action or customer approval.
- **Windows red-first, actual.** On Windows 11 Python 3.11.9 the old valid three-screenshot observer test failed 0/3: os.O_NOFOLLOW does not exist. Native code pins a non-reparse Windows directory handle and opens an exact allowed filename via NtCreateFile with RootDirectory + OBJ_DONT_REPARSE; rejects reparse points, directories, hardlinks; POSIX uses O_DIRECTORY|O_NOFOLLOW with a held directory-relative descriptor. Real Windows symlink, junction and hardlink attacks tested. A separate Mac negative exposed hardlink acceptance before applying single-link fstat; another negative proved that staging refresh alone without held_capture.py fails. The mobile runner now stages and hashes both modules. Security assurances do not extend to all parent ACLs, an authenticated client, or independent code sign-off.
- **Positive scope.** Windows observer 24/24 PASS, native file security eight tests with one POSIX-only skipped, combined 32 OK (one skip). Mac 32 combined OK (one Windows-only skip), separate 49 scoped Python tests OK (one skip), and 37/37 SDA visual/media evidence gate PASS. Exact SHA256 parity of four source/test modules across Mac/Windows is in the tracked manifest. An unrestricted Python unittest discovery invocation produced two existing harness-import errors: test_chrome_shutdown_hang.py calls sys.exit on import, and test_negative_contract_gate.py expects an explicit Chrome receipt directory. THAT INVOCATION FAILED. The supported explicit suites passed; no false full-suite green.
- **Real Chrome and visual inspection.** Exact code SHA dec72e7... passed 6/6 existing Playwright mobile, 320px phone, tablet, desktop, stale-observer and disconnect controls. Visually inspecting a first-fold screenshot exposed a misleading broken image and diagnostic error when capture lacked a verified hash. The fix keeps the image hidden and displays a clear preview-unavailable placeholder until SHA-checked bytes decode. New empty-state assertions passed. Fresh 3/3 Chrome screenshot captures of Run21 checked source, viewport and PNG byte fingerprints. Real browser viewer tests then passed 57/57 across mobile/tablet/desktop. Private client-friendly MacBook localhost preview: http://127.0.0.1:8880/studio_internal/sda-native-verified-dKWJ9J0L/ . Its read-only observer updates status every 15 seconds, images expire after 10 min without a new verified browser capture. This is a snapshot and a status heartbeat, NOT livestream or an authenticated client portal.
- **Media check.** FFprobe confirms Business Card candidate 60s H264 video with AAC start/end aligned at 0ms and RestoreAssist 60s H264 visual-only without audio. Six chapter VTT timings cover 0–60s but are NOT approved narration/caption synchronisation. Rights and creative approval remain absent.
- **Proven upstream and review gap.** Canonical manifest pins CleanExpo/Pi-Dev-Ops commit 373e65ad33156deb10fbdb1c2bc33f39f925a7fb, still missing remotely: authenticated GitHub lookup 422. Portability checker still reports drift in visual-qa decision log. Both read-only subscriber CLI reviews (Codex and Claude) timed out with exit124 and NO completed independent exact-SHA verdict. JEV NOT RUN. Mac Mini Commander offline/SSH exec failed; Windows Chrome and Job Object process watchdog NOT run.
- **RELEASE HOLD** pending signed independent exact-head review and PR CI, governed remote canonical source, three-machine browser/watchdog parity, authenticated tenant-aware approvals, media caption/rights clearance and a full accepted website-design session. Evidence includes raw Windows/Mac red-first and green test logs, browser receipts, media ffprobe, source fingerprints and a SHA256 manifest at skills-library/sda-localhost-review-prototype/evidence/20261031_windows_native_held_read/. Actual PNG screenshots remain ephemeral private files and are not committed.

### 2026-10-31 18:xx AEST | SDA mobile-first visible workflow (RA-6473)

Real visual review exposed a 4498px phone screenshot placed before detailed progress. In isolated feature worktree feat/sda-accessible-scroll-20261031, a scrollable, keyboard-focusable, exact-hash image viewport with ARIA Expand/Collapse controls and mobile progress-first ordering now caps image display to 520/630/639px on phone/tablet/desktop. Before-change Chrome regression FAILED as expected; after change 3/3 viewport passes and wrong PNG substitution was correctly rejected while release remained HOLD. Mac 49 supported Python tests OK (1 OS-specific skip), SDA visual/media 37/37 PASS; initial broad discovery lacking required negative-contract fixture logged one ERROR, not hidden. Mobile browser screenshot visually inspected. All raw results, hashes and limitations are in skills-library/sda-localhost-review-prototype/evidence/20261031_mobile_scroll_ux/. No customer auth, independent exact-SHA model signoff, canonical upstream PR, Windows Chrome proof, Mini SSH completion or media rights authority. No push/merge/deploy/release.

### 2026-10-31 18:3x AEST | Exact-source served Chrome, cross-machine partial and media stream receipts (RA-6473)

Built an actual local-only private HTTP 200 viewer at http://127.0.0.1:8880/studio_internal/sda-accessible-verified-r32-20261031/ with exact HTML SHA-256 bbf79ca5ba5ed835f9bec8336733abb97d8ce9af529401d01197129d6967b215, and observer reading isolated Git HEAD every 15 seconds. Under OS-process watchdog, real Chrome recaptured three exact-source screenshots at 390x844, 768x1024, 1440x900, 3/3 passed, held privately with SHA manifests rather than committing duplicate binary images. Separate Chrome tests fetched actually served HTML and checked SHA bytes, HEAD, SHA-verifiable PNGs, progress before image at narrow sizes, accessible expand/collapse, client/expert toggle, release HOLD, zero JavaScript errors and third-party requests, 3/3 PASS. Raw test code, logs, watchdog JSON and hashes preserved in evidence/20261031_mobile_scroll_ux. No tenant auth or signed approval exists.

Windows native Chrome tested exact byte-identical HTML SHA with isolated synthetic status but no screenshot: phone 390 and tablet 768 PASS, desktop Playwright click stability/screenshot hung under real load; no 3/3 Windows claim. Initial failure and bounded retry evidence retained; third attempt pending. Mac Mini Commander offline and SSH exec request failed: no Mini Chrome replay.

Media ffprobe: business-card candidate video H264 1280x720 60s and AAC mono 48kHz 60s with 0.000s start/end drift; RestoreAssist H264 1280x720 60s has NO audio. Two WebVTT chapter files have six chronological cues spanning 0 to 60s but NOT narration captions, rights or transcript alignment proof. GitHub read-only canonical Pi-Dev-Ops exact commit 373e65ad33156deb10fbdb1c2bc33f39f925a7fb returned 422 No commit found, and portability reports one visual-qa decision-log drift. No Claude/Codex/JEV exact-commit verdict in this run. RELEASE HOLD. No push, merge, public deployment, paid API, client approvals or publication.

#### Windows native Chrome bounded third attempt (31 Oct 18:36 AEST)

After phone/tablet passes and a failed desktop click (30-second timeout), a desktop diagnostic attempt failed on 30-second screenshot timeout. Third and final bounded desktop-only real Chrome run succeeded on the same independently SHA-matched HTML, including actual expand/collapse interaction. This proves all three sizes have separately passed but not that a full three-viewport Windows run is stable or production ready. Original failing logs are preserved byte-for-byte in lossless gzip with SHA digests, and the passing desktop log is retained. No further Windows retries in this run; desktop stability under load needs follow-up. Exact evidence in evidence/20261031_mobile_scroll_ux/windows_browser_attempts.json. Commercial release HOLD.


### 31 October 2026, 21:02 AEST | RA-6473 | SDA truthful client-brief state

Clean isolated review branch `feat/sda-brief-failclosed-20261031` at exact code commit `db7e226d7a1f1471012a4dc0599b7db28f1259f9` (base `01c481e6`). The original dirty `~/.claude-worktrees/sda-visual-qa-20261031` and dirty `~/Pi-Dev-Ops` root were **not edited**. Discovered an actual misleading client-facing status: Run 21 browser snapshots caused `Understand the brief` to display `done` with no authenticated client brief. New red-first test failed with `done != review`; after code fix, 25/25 observer tests and 37/37 SDA evidence tests passed. Live Chrome: three fresh Run 21 source-bound captures, 3/3, and 57/57 actual browser checks across phone/tablet/desktop on a separate localhost candidate. Visual inspection showed the client brief warning on the mobile first screen and beside progress on desktop. Exact-commit replay `db7e226d` showed 57/57 Chrome, release HOLD, and local test receipt bound to SHA but explicitly **UNSIGNED** (`testsTrusted=false`).

Live local read-only candidate: `http://127.0.0.1:8880/studio_internal/sda_brief_evidence_candidate_2049/`. The source screenshots are SHA-256 byte-checked and time-labelled, **not a live video**. Candidate status was observed from a one-shot refresh only. Seven existing SDA observer workers were detected, so no eighth perpetual worker was launched; the candidate becomes visibly stale until refreshed. Complete raw red/green receipts, Chrome manifests, cross-device screenshot SHA-256 checksums, fresh ffprobe stream JSON, and an immutable receipt manifest are in `skills-library/sda-localhost-review-prototype/evidence/20261031_brief_state/`. Fresh ffprobe reconfirmed 60-second H264+AAC Business Card candidate and silent 60-second RestoreAssist candidate; narration-aligned caption evidence and commercial rights remain unverified. A missing client brief is not compensated by screenshots. Canonical Pi-Dev-Ops pin `09e63e79bf33a7d6688b0a9e1fbe1f14e1baaf68` returned GitHub HTTP 422: remote portability still blocked; no pin update without publication evidence. Mac Mini currently offline, no Windows/CI replay of this new SHA. No authenticated tenant approvals or commercial publication rights. **Commercial release HOLD; no push, merge, deploy, paid API or release action.**


### 31 October 2026, 21:2x AEST | RA-6473 | SDA capture expiry is a client trust boundary

On clean, isolated `feat/sda-capture-freshness-20261031` (source commit `72765013a774ecf6dd9b2a62c04deaa35ffe351f`), a real Google Chrome red-first regression revealed the private viewer could display a screenshot **20 minutes old**, a screenshot explicitly marked capture-fresh=false, or a future-dated screenshot as though current; it could also leave already verified pixels visible after its observer disconnected. Chrome negative controls with original Run 21 PNG bytes returned **3/7, four expected failures**. This was not the broken harness's initial `URL is not a constructor` setup error, which was corrected before collecting the valid red-first receipt.

The viewer now refuses to fetch expired, future or invalid screenshots and clears a previously verified image on disconnect. It leaves a plain-English **UNVERIFIED SNAPSHOT** message, never approval/release. After repair and exact source commit, **7/7 genuine Chrome adversarial checks**, **57/57 client viewer Chrome checks** across mobile/tablet/desktop, **25/25 MacBook Python observer checks** and **37/37 SDA evidence gate checks** passed. Tablet, desktop and mobile actual browser render screenshots were inspected; the project steps remain visible before the oversize preview on small devices. The viewer-browser harness's deliberately synthetic capture timestamps are enabled only after checking original screenshot SHA-256/byte lengths and are not evidence of a fresh live capture.

The Mac Mini was online this run: exact source file SHA-256 matches MacBook across six files, and isolated Mini internal `/tmp` replay passed **25/25** observer tests and both Node syntax checks. Windows was online and responded to read-only PowerShell/git commands, but **this new exact source was not installed nor browser-tested on Windows**. Full Mini Chrome and signed CI were not run. No other agents or existing worktrees were stopped or altered.

Fresh ffprobe confirmed Business Card candidate H.264 video + AAC audio both exactly 60 seconds with 0 start/end drift; RestoreAssist H.264 visual candidate is 60 seconds and has **no audio**. Six VTT scene chapter markers are not narration-aligned, licensed commercial captions. Canonical Pi-Dev-Ops manifest owner remains pinned locally at `373e65ad33156deb10fbdb1c2bc33f39f925a7fb`, but a fresh authenticated GitHub API check returned **HTTP 422 No commit found**. Five files in the root Pi-Dev-Ops checkout are dirty. Its ownership/pin was therefore not rewritten or treated as portable. Claude, OpenAI/Codex and JEV were **not independently run against this exact SHA**; there is no dissent to claim. No signed PR review, authenticated tenant/client approval, merge, push, deploy, external publication, paid API or commercial clearance. **RELEASE HOLD**. Full red/green receipts, media probes, source SHA and evidence hashes: `skills-library/sda-localhost-review-prototype/evidence/20261031_expiry_guard/SHA256_MANIFEST.json`.

Next: independently review exact SHA and reconcile canonical upstream owner via a governed signed PR before changing manifest/pin; repeat Chrome on Mini and Windows with exact source; implement tenant-authenticated brief/approval and human rights clearance. Do not mistake local session screenshots for an authenticated end-to-end delivery.

#### Served-browser addendum, 31 October 2026, ~21:35 AEST

A separate one-shot MacBook localhost page was built at
`http://127.0.0.1:8880/studio_internal/sda_freshness_live_candidate_aQlkVW/`.
Real Chrome recaptured original Run 21 at phone/tablet/desktop: **3/3 source captures**.
The final evidence-branch SHA at observation was
`b6989689627de6922a037285bd8c83af3bd64b04`; an exact-version direct
37/37 local gate receipt was generated marked `independentSigned=false` and
`releaseAuthority=false`. The read-only observer produced three source-bound,
SHA-verified screenshots while keeping **RELEASE HOLD** and the first task
`Confirm the client brief` in **review**.

First *direct-served* Chrome harness returned 0/3 only because its test
misclassified local `blob:` image URLs as third-party network requests. This was
a **test harness false negative**, not an external request or the viewer
security defect. After classifying only HTTP(S) network requests for egress,
**3/3 direct unmocked Chrome tests passed** (390, 768, 1440px), with zero
JavaScript/console errors, zero actual third-party HTTP(S) requests, disabled
approval controls, correct task and release HOLD. Exact PNG screenshot hashes
and both initial/final raw JSON receipts are retained in the
`evidence/20261031_expiry_guard` directory. The actual browser PNGs are
in the private localhost session folder, not Git; only hashes and metadata
are versioned. This candidate's observer ran **once only**; no additional
perpetual worker was launched because other SDA observers already exist.
Its status correctly becomes **STALE**, so this is not a persistent live feed.
No unsigned evidence is client approval, rights clearance or release authority.

## 2026-11-01 12:30 AEST — RA-6473 Pi-Dev-Ops canonical owner review round 2 repairs

- **Authoritative pre-fix Git head:** 08d4bc99f7c8fd39e7b1d7fcee787b636b507a34; upstream origin/main 8e3c564f9b26f99e067dccd89c73822306d2942b, verified read-only. Isolated worktree /private/tmp/pi-dev-ops-sda-owner-reconcile-20261031; dirty root and alternate candidate remain untouched.
- **Actual independent reviewer:** Codex exact-head report /tmp/sda-pdo-review-round2-20261101.json, verdict FAIL, three P1s. (1) Untrusted FIFO could block manifest/screenshot evidence gate; (2) documented command called an older installed script lacking scope and baseline arguments; (3) installer returned error when a valid global hook and unrelated existing local settings coexisted. Do not record reviewer approval: verdict FAIL. JEV not run; no JEV dissent or signoff.
- **Red-first evidence:** installer-red.txt: 8 run, 1 ERROR; gate-red.txt: 43 run, 2 ERROR (real 1.5-second FIFO timeouts) + 1 FAIL (stale documented CLI). Source unaffected at red point.
- **Targeted repair:** open final evidence fd using O_NONBLOCK|O_NOFOLLOW and reject all nonregular files using fstat; check global hook registration even with existing local settings, never mutate settings; make all three skill documents point at exact SHA-reviewed Pi-Dev-Ops source and require external --scope-record for technical verification. This does NOT validate a claimed human signature or fix a stale installed copy.
- **Green receipt:** installer-green.txt 8/8 PASS; gate-green.txt 43/43 PASS; router existing suite 4/4 PASS; git diff --check PASS. These are UNSIGNED developer tests, not independent review, CI or release approval.
- **Local CI preflight:** gate-parity passed 24 covered, 10 explicitly exempt, zero unmapped. Mandatory file-length gate FAILS for two new standalone files (sda_evidence_gate.py 577 lines, test_sda_evidence_gate.py 604 lines). Mandatory function-length gate FAILS for three newly introduced functions (check 365, png_dimensions 50, GateTests.release_fields 46). Deliberately did not weaken/update lint baselines. These must be refactored and independently reviewed before publishing.
- **CI mirror:** previous mirror source obsolete; exact 08d4bc99 mirror was stopped by remote-execution safety and has no valid complete PASS receipt. Never bypass safety. No branch push, PR, merge, deploy or installed hook mutation until full genuine CI, independent exact-head PASS and signed pr_release_gate receipt.
- **Order and blockers:** (1) refactor new long functions/files without lowering CI bars and wire the standalone suites into CI; (2) run complete relevant local/remote CI and fresh independent exact-head review (previous FAIL does not transfer); (3) sign gate, ordinary branch push, protected PR and governed main merge; (4) then re-vendor exact published owner SHA into skills-library and only then distribute to Mini, MacBook, Windows. Never overwrite dirty roots. Technical green cannot certify creative quality, rights or tenant acceptance.

Receipts are relative to repository path evidence/sda-pdo-review-round2-20261101/. SHA-256 fingerprints are recorded there; signed/remote status HOLD.

## 2026-11-01 12:45 AEST: RA-6473 canonical-source modular release candidate

- The previous independent Codex exact-SHA review of 08d4bc99 was FAIL (three P1 findings). Reproduced all three red-first and repaired them in 4dc7b10b, not merged or pushed. The present modular source has NO new independent approval.
- Replaced the oversized 577-line gate with a 64-line entrypoint and separate secure file, screenshot, Chromium, actual film/FFprobe and creative release modules. Split 604-line evidence tests into fixture plus modular core/adversarial suites. No lint-baseline edits.
- New real negative test malformed-metadata-red.txt: candidate-controlled reviews field as a list raised AttributeError (1 test, 1 error). Corrected nested JSON object validation and verified positive cases.
- Earlier modular-local-validation.txt is retained as FAIL: two 1.5-second FIFO watchdog timeouts under competing MacBook CPU load. Increased watchdog to a still-bounded 5 seconds. modular-local-validation-r2.txt and local-validation-meta.txt record EXIT=0: 44/44 gate, 8/8 installer, 4/4 router; file-length zero new/grown, function-length zero new/grown, gate parity 25 mapped covered / 10 exempt / 0 unmapped, bash syntax and git diff whitespace passed. Function-length scan reported one pre-existing unparsed app/server/scanner.py. Do not call this full CI.
- Added explicit CI Python job for all 3 standalone SDA suites, matched by the existing handoff-loop.sh and gate-parity.map.json. Full hosted CI/mirror is NOT verified; the prior exact-08d4 CI mirror was blocked by remote safety. Never bypass safety restrictions.
- Read-only MacBook localhost GET checks: Run21 baseline HTTP 200 and Run15 viewer HTTP 200 at 12:43:52 AEST. This is not visual, rights, audio or creative acceptance.
- HOLD: independent exact-final-SHA review, genuine full CI, signed pr_release_gate receipt, governed branch push/PR/remote checks and main merge remain unmet. No version pin or cross-machine consumer rollout before canonical main is verified. Dirty checkout and active agents unchanged. JEV did not run, no dissent is attributed.
- Immutable negative, positive and source-fingerprint receipts are in evidence/sda-pdo-review-round2-20261101/.


## 2026-11-01 13:32 AEST — RA-6473 canonical Pi-Dev-Ops owner review round 3 repairs (UNPUBLISHED)

- **Live provenance re-read:** clean isolated worktree `/private/tmp/pi-dev-ops-sda-owner-reconcile-20261031` was at `4995614da7b01b1b3dc8c678af2eec4c14169d75` before changes; `git ls-remote origin refs/heads/main` returned `8e3c564f9b26f99e067dccd89c73822306d2942b`. The original dirty root and competing candidate were not modified. No SHA was inferred from the original task instructions.
- **Existing independent review reused, not duplicated:** actual Codex review at `/tmp/sda-pdo-review-round3-20261101.log` (matching HEAD `4995614d`, completed EXIT=0 for the tool, substantive verdict **FAIL**): two P1s (stale `agentskills.json`/`.yaml` after SKILL changes; FFmpeg tolerated an invalid 25s packet while exiting 0) and three P2s (installer default wrote nonloaded user local settings; custom `--hook` validated one file but registered another; router injected a stale CLI missing independent records). The verbatim findings and log SHA-256 `14aafc7da61232aee2e80e7eb0ce2b9513a48d831d58a114f22708eb7707838e` are retained in `evidence/sda-pdo-review-round3-20261101/`. This FAIL cannot approve repaired code. No authorised Jev work occurred.
- **Red-first, actual negative receipts:** `media-red.txt` showed 1/1 FAIL because a simulated FFmpeg zero-exit result containing `Invalid data found when processing input` was wrongly accepted. `installer-red.txt` showed 2/2 FAIL: non-loaded default settings path and hardcoded executable despite a validated custom path. `router-red.txt` showed 1/1 FAIL: current CLI lacked `--scope-record` and `--baseline-record`. `manifest-red.txt` lists both stale manifest SHA-256 values. `installer-green.txt` also retains a new real idempotency failure found during correction (10 tests, one error).
- **Code corrections in isolated owner only:** FFmpeg full-master decode now uses `-xerror -err_detect explode` and rejects any error stderr even if exit status zero; regression asserts fatal flags. Installer uses the path it actually validated, shell-quotes paths, checks decoded hook entries for idempotence, defaults to Claude Code's loaded user `~/.claude/settings.json` and refuses to overwrite an existing unrelated file. Router text now invokes the reviewed checkout with independent `--scope-record`, release-only `--baseline-record` and explicit HOLD for real rights/tenant authority. Official `python3 -m swarm.agentskills_manifest` regenerated both manifest files with only the two SKILL hashes and package patch version `1.25.24` changed. A second generation produced byte-identical hashes, so the manifest gate is idempotent.
- **Actual positive tests:** MacBook modular evidence **45/45 PASS** (`gate-green.txt`), installer **10/10 PASS** (`installer-green-r2.txt`), router **5/5 PASS** (`router-green-r2.txt`). Mac Mini on scoped archive `4b5d4564625637244767d1f909378660edcf309ad6f780251fcca589f4ec3215` returned native Python 3.14 **45/45 + 10/10 + 5/5 PASS**, with real source-transfer hash verified and logs copied into the evidence folder. No production machine install or release occurred.
- **Mandatory local checks:** file-length PASS (2019 files, zero new/grown; old shrink warnings); function-length PASS (14659 functions, zero new/grown, **one pre-existing unparsed** `app/server/scanner.py`); gate parity **25 covered / 10 exempt / 0 unmapped PASS**; frozen-path manifest 44 patterns/91 tracked files checked; manifest regeneration idempotent; `git diff --check` and bash handoff syntax PASS. Not a claim of full hosted CI or Windows browser acceptance.
- **HOLD:** genuine relevant hosted CI remains unverified after the older CI mirror's remote-safety block; independent PASS on the subsequent exact reviewed HEAD and signed `pr_release_gate` receipt have NOT yet occurred. No ordinary feature push/PR, merge to canonical main, skills-library re-vendor, cross-machine install, client creative/rights signoff, paid API, force push, bypass or deployment. Until the exact owner main commit is published and verified, skills-library pins and consumers must remain unchanged. The Run15 localhost page remains private evidence, not a tenant-authenticated acceptance portal.

## 2026-11-01 14:23:20 AEST — RA-6473 Pi-Dev-Ops canonical round 4 P2/P3 repairs, still HOLD

- Existing independent Codex report reviewed exact pre-fix SHA
  209121ab738ce7b52cbaf626a25c1be49a0f7168: 2 P2 + 1 P3,
  NOT PASS. Actual report log SHA256 74b8258c3bf602c4127022e350e42d4913cccbe182c612b91ccc9b0ed5931512.
- Red-first: uninspected alternate audio produced an empty errors array
  (1 test FAIL); malformed nested reviewer crashed instead of HOLD
  (1 ERROR); two mismatched router paths falsely reported installed
  (2 FAIL). All raw negative receipts are preserved in
  evidence/sda-pdo-review-round5-20261101/.
- Fixed only in isolated owner branch: unsupported extra streams now
  fail closed; single A/V streams decoded explicitly; malformed reviews
  produce HOLD; installed router identity matches resolved validated path;
  conflicting global settings refuse safe automatic installation.
- Scoped green: MacBook 47+12+5; Mac Mini Python 3.14 47+12+5.
  Mini byte-identical test archive SHA256
  8568164a9ea858788f5a6495cf8be759f964807bcdfb73a5ef730b7fb66b7454.
  An initial incomplete Mini test transfer failed due to omitted SKILL.md;
  corrected transfer passed and both cases remain documented.
  File/function-length and local parity checks PASS; one pre-existing
  parser warning remains. This is NOT full hosted CI.
- Next exact-source Codex independent review, genuine full relevant CI
  and signed PR release receipt are required BEFORE branch push/PR/main.
  Earlier CI mirror safety block remains, never bypass. No ecosystem
  publication, Windows installation, creative/rights signoff, or JEV work.
  Private localhost HTTP 200 is only reachability, not approval.

## 2026-11-01 14:34:42 AEST — RA-6473 canonical round6 scope binding, HOLD

- Reused exact pre-fix 0a7cbfc5 Codex review, tool exit 0 but substantive
  3 P2 findings, no independent PASS. Log SHA256 e61f833e7b9f51de8669c4322f3aae7f0da08a2cc0aa8677c0451efdc76678be. No JEV.
- Red-first three tests FAIL on original code: old founder approval survives
  desktop screenshot mutation; old creative reviews survive modified source;
  embedded subtitle mismatch accepted. After repair, 3/3 targeted green.
- New canonical digest binds all scoped screenshots, audit and candidate/film
  to both creative reviews, comparison and founder approval. Unsupported
  embedded subtitle or other unverified streams HOLD. Records do NOT
  authenticate users or establish rights. Corrected installer guide.
- Full MacBook scoped 50+12+5 PASS. Mac Mini exact temporary source archive
  a444bef723d0e973c30d362df9a68e7c75872b65520b848f8c474cef69d49aff
  reproduced Python3.14 50+12+5 PASS. Earlier Windows source: installer
  12 and router 5 PASS; secure evidence 47 cases fail (43 FAIL, 2 ERROR)
  because POSIX dir_fd/no-follow unavailable. Native Windows rollout HOLD.
- Local file/function length and gate parity PASS, one pre-existing
  scanner.py parse warning. No full CI, no new exact-source independent
  verdict, no signed pr_release_gate, no branch publication or merge.
  Remote CI safety check NEVER bypassed. Canonical before skills-library.
- Durable receipts evidence/sda-pdo-review-round6-20261101/.

## 2026-11-01 SDA WSL2 secure-evidence portability, isolated HOLD

- Existing canonical owner candidate cfa69d39 is dirty and untouched; new isolated test-only Git worktree feat/sda-wsl-evidence-parity-20261101 based on cfa69d39, without a duplicate clone.
- Native Windows (Win32 Python) remains unsupported because O_NOFOLLOW/openat unavailable. Existing WSL2 Ubuntu on the authorised Windows PC runs on Linux/ext4 and **7/7 real secure-file tests PASS**, source SHA256 matches MacBook and Mini; both Macs also **7/7 PASS**. Tests include real symlink-root/parent/leaf, mutated SHA, file cap and FIFO attacks.
- Windows WSL Ubuntu has no ffmpeg or ffprobe; first full fixture setup ERROR, no full Windows evidence/media acceptance claimed. Never put evidence on unverified NTFS/UNC paths for a claimed POSIX security guarantee.
- Receipts with exact source hashes, original host test logs and scope limits: evidence/sda-wsl-posix-parity-20261101/ on this isolated branch. Local scoped code/test progress only: no CI, signed PR release, independent exact-head review, native Windows gate, rights approval or ecosystem publication.
- The new `test_sda_gate_posix_secure_io.py` is included in the existing CI unittest discovery pattern. Local MacBook discovery **57/57 PASS**, log SHA256 `14c6a2ed84bd0598d91b8e267b6b6ac9637749a4f16ccd2642d22a15b8d0f8d4`; hosted CI and signed release are still HOLD.

## 2026-11-01 SDA isolated round-7 regression + WSL parity reconciliation, release HOLD

- Preserved the dirty canonical Pi-Dev-Ops owner worktree, all other worktrees and existing agent processes. Reused the clean WSL2 POSIX secure-file parity branch without cloning the repository; new independent review worktree only.
- Actual red-first tests: unknown critical PNG chunk and boolean creative findings both erroneously returned empty errors before source repair (2 FAIL); exact fixes from the existing dirty round-7 candidate applied only to this isolated branch; same 2 tests PASS.
- MacBook local discovery 59/59 SDA + 12/12 installer + 5/5 router PASS; Mini same exact source archive SHA256 e2f6ee5018bb0c5f279a4afc2757d424fa488962899b4b9fd765ec7619f4defd 59+12+5 PASS. Initial Mini missing fixture ERROR preserved; complete source rerun PASS. Existing Windows WSL2 7/7 secure-file result remains valid because secure core and test SHA256 are unchanged; Windows full media prerequisites and native Win32 remain HOLD.
- Local file-length, function-length and CI-parity checks PASS with one pre-existing parser skip. None proves hosted CI, creative signoff or release authority.
- No completed independent review of the combined exact code SHA, genuine full hosted CI or signed pr_release_gate. No push, merge, deployment, tenant approval, rights clearance or three-machine commercial rollout. Evidence: evidence/sda-r7-wsl-combined-20261101/.

### 2026-11-01 | RA-6473 | Canonical PNG evidence chunk-order regression (isolated)
- Decision: reject PNG screenshots whose IHDR is not first, IDAT pieces are non-contiguous, or PLTE follows image data. A matching SHA-256 does not make malformed image bytes credible.
- Negative proof: 3 failing tests before repair; positive proof: 4/4 focused and 63/63 scoped MacBook tests, 4/4 Mini exact-source tests, plus three earlier real Chrome capture PNGs decoded. Evidence: evidence/sda-png-order-r11-20261101/.
- Dissent/release: no new independent verdict or JEV work; full hosted CI/signed gate unavailable; Windows newest source not retested. HOLD. Original dirty owner worktree untouched. No publish/merge/deploy/tenant acceptance.

### 2026-11-01 18:26 AEST | RA-6473 | FFmpeg media confinement P1, isolated candidate (HOLD)
- An actual independent read-only Codex review of **prior exact SHA 0fed29a0** found P1: media auto-detection can treat a SHA-verified `master.mp4` as a reference-based HLS/concat file and access external resources. It also identified delayed-start container timeline P2 and global hook checkout-relative path P2. Review log SHA256 `5c4e6b5ef80a153a859a83f83ed80175dda0765a4fc2dfd2794b7b236796f5f3`. That FAIL verdict cannot approve newer SHAs. No JEV work claimed.
- Isolated worktree `/private/tmp/pdo-sda-media-confinement-r12-20261101`, branch `feat/sda-media-confinement-r12-20261101`, starts from clean `e5e282ef`. Dirty canonical owner and unrelated agents' checkouts untouched; no duplicate full CI mirror/review spawned.
- **Red-first**: five adversarial media tests against the old implementation yielded **4 FAIL + 1 ERROR**, covering unbounded FFprobe, FFmpeg decode, frame extraction, HLS playlist probing, and aligned but 30-second-delayed tracks. Stored in `evidence/sda-media-confinement-r12-20261101/red-first.log` and original exit code.
- **Fix**: reject non-ISO-BMFF/MP4 `ftyp` payloads **before any FFmpeg invocation**; force the `mov` demuxer with file-only protocol and disabled external data references/absolute paths for probe, full decode, and frame extraction. Validate stream starts against zero and video end against container end. Full valid 60-second synthetic video/audio+frame pipeline remains accepted.
- **Green**: new tests **5/5 PASS**; initial broad test run **67/68** exposed a pre-existing error-precendence assertion conflict from new container check (original failure retained); repaired ordering without weakening either check; final **68/68 MacBook PASS** and **68/68 Mac Mini PASS**. Installer **12/12**, router **5/5** on both machines. Mini source archive hash `3c35be3862d2fa87a6a6ac80d7c427f232e3620c6e2ff11cc62978d083c4835f`, transferred and unpacked on Mini internal `/private/tmp`, not flaky external SSD. `git diff --check` PASS.
- Release HOLD: no independent review of this **new exact commit**, no genuine full hosted CI or signed `pr_release_gate`. Windows WSL2 full film suite still lacks FFmpeg/FFprobe. Global user hook absolute reviewed-path P2 not fixed in this candidate. No authenticated tenant approvals, creative/rights signoff, caption-word match, push, PR, merge, deployment, paid API or bypass. Pi-Dev-Ops remote main checked at 18:26 AEST: `8e3c564f9b26f99e067dccd89c73822306d2942b`.

### 2026-11-01 19:33 AEST | RA-6473 | SDA isolated P2 hook and comparison repair, local only (HOLD)
- Reused the actual completed independent Codex review on older exact e1d35bac, with three P2 findings. No duplicate reviewer or mirror was spawned. Edited ONLY clean isolated feat/sda-media-confinement-r12-20261101, not dirty canonical owner or other agents' worktrees.
- Red-first: invalid visual observations had five failing subcases; checkout-relative global hook failed; real user-global SDA registration was missed by project-local installer (ERROR); PNG function-length 46-line FAIL. First hook patch also gave prepare 42 lines and FAILED local function lint; extracted helper without changing baseline.
- Source fixes: CRC/PNG chunk extraction; require real nonblank comparison observations; PIN ROOT via absolute PI_DEV_OPS_ROOT and signed exact SHA guidance; check actual user-global Claude settings before create-only project installation. Existing settings never overwritten.
- MacBook positive checks SDA 69/69, router 6/6, installer 13/13. Mini exact-archive byte parity e8c469c6016c0b6efd965066db0c23c70ab3c97377004df3cdc248c79cc649c1, same 69+6+13 PASS. Local function/file-length, CI-parity (25/10/0), git diff checks PASS. Known scanner.py function parse skip not concealed. Raw receipts and source SHA in evidence/sda-png-lint-comparison-r13-20261101/.
- Latest new SHA needs independent exact-SHA PASS, full relevant hosted CI and signed pr_release_gate before any protected PR/merge; Windows latest media tests, commercial rights/creative acceptance and authenticated tenant approvals remain HOLD. No new JEV, no paid API, no push/merge/deploy/force/hook bypass.

### 2026-11-01 20:31 AEST | RA-6473 | Manifest symlink bypass repaired in isolated SDA owner source (HOLD)

- In existing clean r12 Pi-Dev-Ops worktree only: two red-first manifest-path symlink tests reproduced `Path.resolve()` erasing a symlink before no-follow verification. Root and leaf aliases both failed new expectations.
- First patch caused 53 real test failures on macOS due its fixed /var system alias; retained as negative regression, then narrowly normalised only expected macOS /var, /tmp, /etc system aliases without resolving any deeper candidate-controlled links.
- Final MacBook 71/71, Mini exact-source 71/71 SDA evidence tests PASS; installer 13/13 and router 6/6 MacBook PASS. First Mini run's one missing-document test fixture error is retained, fully rerun after adding only absent documents.
- File/function-length lint and CI gate mapping PASS locally, existing scanner.py parse skip noted. Immutable logs and source hashes stored in evidence/sda-manifest-symlink-r16-20261101/.
- No new independent exact-commit approval, genuine hosted CI or signed release-gate receipt. This work is local-only; no main merge, skills-library re-vendor, client authentication, commercial/creative/rights signoff or JEV work. No code publication or spending.

### 2026-11-01 21:25 AEST | RA-6473 | Independent R16 exact-head P2 repairs in isolated R17 (HOLD)

- Reviewed existing completed Codex exact-SHA c8e15f2a log, no duplicate heavy reviewer or CI mirror. Two concrete P2 findings reproduced in a newly added red-first regression file: 2/2 FAIL before source changes.
- Rejected candidate manifest path traversal (`..`) before descriptor-confined evidence access or independent record comparisons. Stopped using coded MP4 dimensions as a proxy for FFmpeg's actual auto-rotated PNG output; preserved SHA-verifiable exact-frame byte equality and PNG parsing.
- Positive MacBook 2/2 targeted and 73/73 full SDA discovery; local file/function-length and CI parity 0 exit; real Mac Mini 2/2 focused exact-source archive on internal /private/tmp, archive hash in evidence/sda-review-p2-r17-20261101/.
- No current exact-fix independent PASS, signed pr_release_gate, hosted CI, JEV, new Windows/tenant/rights/creative acceptance or authorised publication. Protected main and other agents' work remain unchanged.

### 2026-11-01 21:34 AEST | RA-6473 | Independent R17 review finds CI test-discovery omission (HOLD)

- The completed Codex review against exact 4037b7cf ran to process exit 0 but returned a real **P2**, not release PASS: both `.github/workflows/ci.yml:193` and `scripts/handoff-loop.sh:212` use `test_sda_gate_*.py`; the new R17 test is named `test_sda_review_p2_r17.py` and is omitted.
- Direct red-first discovery assertion proves all SDA tests = 73, both CI/handoff discovered tests = 71, exit 1. Retain output in `evidence/sda-ci-discovery-r18-20261101/` without treating a partial CI run as acceptance.
- A focused attempt to correct filename/discovery was blocked by execution safety controls. No reroute or bypass occurred. Existing source code and 4037b7cf HEAD remained unchanged after the block; do not claim remediation.
- Windows Ubuntu WSL2 independently ran the same scoped archive SHA `fcec9d0c3f23d223c284973d58d49b93a7c44ec98f857c857fe00727cb805190`: one manifest test PASS, rotation test SKIP because FFmpeg/FFprobe absent. Private Run15 localhost returned HTTP 200 only.
- Pending: safely restore mandatory test discovery, repeat exact-head independent review and real hosted CI, issue/verify signed pr_release_gate, then governed protected PR merge and exact source re-vendoring. No commercial rights, JEV, creative acceptance or tenant control claimed.

### 2026-11-01 22:22 AEST | RA-6473 | CI discovery P2 corrected in isolated R12 branch (HOLD)

- Reused previous completed exact-head independent R17 review, the original 73-vs-71 red-first receipt and existing clean R12 worktree. Canonical owner/skills-library dirty worktrees and other agent changes were not touched.
- Repaired the same missing-test discovery in both `.github/workflows/ci.yml` and `scripts/handoff-loop.sh` by changing only `test_sda_gate_*.py` to `test_sda_*.py`. Installer and router discovery remain unchanged.
- Added `test_sda_gate_ci_discovery.py` which enforces that both runners cover every `test_sda_*.py` module, including the two previously omitted P2 regressions.
- Actual MacBook run: 74/74 SDA source tests PASS, 13/13 installer PASS, 6/6 router PASS; bash syntax and Git diff whitespace PASS. Raw outputs and source hashes in `evidence/sda-ci-discovery-r19-20261101/`; original red-first output remains preserved in the committed R18 evidence.
- This is a **local correction only**. Exact new SHA review, full relevant hosted CI, signed pr_release_gate and protected PR merge have not passed. Mac Mini/Windows latest-source tests, authenticated tenant approval, creative/rights acceptance and owner reconciliation are not complete. Do not market this as a release or customer portal.
