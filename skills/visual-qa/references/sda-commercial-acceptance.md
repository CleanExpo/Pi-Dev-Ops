# SDA visual and commercial evidence gate

**Status:** installed locally on MacBook. Canonical CleanExpo/skills-library
PR and shared Mini/PC installation still require authorised sync; do not
report those as completed.

The installed Claude gate may lag the source. Set PI_DEV_OPS_ROOT
to the absolute clean Pi-Dev-Ops checkout matching the signed review SHA,
then use the script there. Verify git -C "$PI_DEV_OPS_ROOT" rev-parse HEAD
and hold if the review hash differs.

## Technical gate
1. Preserve the prior accepted design and media SHA-256 before a revision.
2. Capture real Playwright Chromium screenshots, 390x844, 768x1024,
   1440x900. Wait for fonts and relevant image decoding. Check visible images,
   resource failures, actual console exceptions, overflows, interactions,
   touch targets, keyboard focus and reduced motion.
3. Include the screenshot SHA-256 and exact audit JSON in one manifest.
4. Run `python3 "$PI_DEV_OPS_ROOT/skills/visual-qa/scripts/sda_evidence_gate.py"
   <evidence-dir>/manifest.json --scope-record <independent-technical-scope-record.json>`. Non-zero exit is HOLD, not final.

## Creative/release gate
1. Inspect real video frames 0,5,10,15,20,30,45,55,59 seconds; visually
   critique typography, pacing, motion, actual imagery and safe areas.
2. Compare against FROZEN accepted baseline using same browser engine/OS,
   writing before/after/diff, never silently updating baselines.
3. Named SDA reviews rubric: hierarchy 20, readability/contrast 15,
   art direction/originality 20, motion/pacing 15, brand fidelity 10,
   responsive/mobile 10, authenticity/rights 10. >=85/100 and every
   dimension >=half. An independent reviewer must review separately.
4. Validate actual licensed assets, truthful claims, current script/voice,
   approved music, captions and end-to-end playback. Then request founder
   approval of exact master SHA; do not infer approval.
5. Run `python3 "$PI_DEV_OPS_ROOT/skills/visual-qa/scripts/sda_evidence_gate.py"
   <evidence-dir>/manifest.json --release --baseline-record
   <separately-frozen-approved-baseline-record.json> --scope-record
   <independent-technical-scope-record.json>`. HOLD until actual review.
6. Gate ensures evidence fields, sha and scoring math, NOT truthfulness of
   reviewer identity, subjective professional quality or legal rights.
   Signed review and commercial-rights receipts must be checked against
   the authorised human decision-maker or the established source-of-truth
   approval/licence record. Jev may supply advisory analysis only. Jev
   cannot attest a right, clear/block release, sign for an owner, or replace
   independent reviewer and founder approval.

## Why not just snapshots?
Playwright documents cross-host font/render variation. Do not compare Mac
screenshots to Linux browser snapshots as though identical. Snapshots assert
pixel regression; they do not evaluate art direction. Never let a passed test
claim a design is commercially approved.

References: https://playwright.dev/docs/test-snapshots
https://playwright.dev/docs/api/class-pageassertions


## Required browser evidence contract

Each `audit.json` page/viewport row needs explicit `status=200`,
`viewport` width, `brokenImages=0`, `overflowing=[]`, `errors=[]`,
a unique `shot` filename and its SHA-256 in the manifest.
The screenshot MUST contain real decodable 8-bit RGB/RGBA PNG bytes; its
width must match the declared viewport and full-page height must meet or
exceed the viewport height. Never invent or omit measurements.

## Frozen baseline record, stored separately

`--release` now requires `--baseline-record /trusted/previous-approval.json`.
This file MUST live outside the candidate evidence directory and contain:
`approved_baseline_sha256` (actual prior-baseline file hash),
`approved_by` and `approved_at`. The candidate manifest has a SHA-bound
`approved_baseline: {file, sha256}` and
`comparison_report: {file, sha256}`. Comparison JSON must identify
the same baseline SHA, the current candidate master SHA and nonempty
observations. The gate verifies that these records agree. It does NOT
authenticate an external human signer, so the reviewer and founder must
also verify the prior approved record against the established source of
truth. Absence of the separately frozen record is a mandatory HOLD.

The installer `python3 scripts/install-sda-visual-hook.py --install`
creates settings atomically **only if absent** using a hardlink. It makes
no backup or replacement of an existing settings file, and NEVER edits
existing security hooks. Global installation still requires its own owner
approval after the reviewed PR.

## Exact technical scope and released-media verification

Always supply `--scope-record /independent/technical-scope.json`, an independently
maintained page inventory **outside** the candidate evidence directory.
The scope JSON must have distinct `expected_pages`, `scope_owner` and
`scoped_at`. A candidate cannot drop pages by shrinking its own manifest.
The reviewer must separately verify the source and authority of this scope
record. This file is *not* permission to publish or a creative acceptance.

The technical gate loads each audited file ONCE, checks SHA-256 on exactly
those bytes, then parses/decodes the same immutable bytes. It rejects
duplicate canonical file aliases and checks each screenshot really
decodes to a PNG of the correct viewport width and at least the viewport
height.

The release gate additionally requires a real playable H.264/MP4 or other
ffprobe-readable video master no larger than 256 MiB per gate run, with
`film.expected_duration_seconds`. It makes an immediately deleted
temporary snapshot of the exact verified bytes, runs ffprobe and complete
FFmpeg decoding, and checks frames at 0/5/10/15/20/30/45/55/59 seconds
against **the exact PNG bytes exported by FFmpeg at each timestamp**.
A still image or fabricated video cannot substitute. Refusal is explicit
when ffmpeg/ffprobe is absent. A larger legitimate master requires a
separate reviewed streaming verifier, not silent weakening of the size cap.
Frame extraction: `ffmpeg -nostdin -v error -ss <second> -i master.mp4
-frames:v 1 -f image2pipe -c:v png pipe:1`.

For technical validation of the five Run14 page areas, a separate scope
record was created in local staging, **not** asserted as founder approval.
The technical gate passed; release must still fail without actual authorised
creative and commercial inputs.

## Safer local hook installer

`python3 scripts/install-sda-visual-hook.py --install` defaults to the
loaded `~/.claude/settings.json` and creates it ONLY when absent, atomically
by same-directory hardlink from a flushed temporary JSON file. It **never
overwrites any existing settings file**. It accepts an existing hook only
when the registered command resolves to the exact validated router path.
A conflicting global SDA router is HOLD, not a duplicate install. For an
existing settings file, the authorised settings editor must append and
review the hook; the installer will not alter it.


## Filesystem boundary hardening (reviewer finding, 31 October)

A separate independent review of SHA `750aadfe` reproduced a real path
time-of-check/time-of-use gap: replacing an evidence file with a symlink
between `.resolve()` and `.read_bytes()` could make an out-of-root file
pass its declared SHA and technical audit. The verifier now uses
POSIX relative directory descriptors with `O_NOFOLLOW` at **every**
directory component and at the final file, and `fstat` and hash/read
use that same opened descriptor. An atomic swap to an outside symlink
must produce HOLD. Two adversarial tests check file and directory swaps.
On a host without secure `dir_fd`/no-follow support, it fails closed
rather than using unsafe path traversal. This intentionally means
release verification may need to run on authorised macOS/Linux equipment
instead of relying on unsafe Windows filesystem semantics.

This hardening verifies containment of evidence files, not authenticity
of a claimed legal licence or human approval. All release authority
checks continue to require independent source-of-truth confirmation.


## Mandatory real audio/video synchronisation checks

The existing fail-closed SDA release gate now probes the **actual master**,
rather than trusting video metadata or screenshots alone. Before any
commercial film is called technically acceptable it must:

- contain a decodable video stream **and** a real audio stream, sample rate
  at least 16 kHz, one or more channels;
- decode completely with FFmpeg (audio and video), match the declared
  approved master duration, and have audio/video stream start drift
  no more than **100 ms**, with end drift no more than **250 ms**;
- include a SHA-bound UTF-8 SRT caption evidence file with valid ordered,
  nonoverlapping caption timestamps within the actual master duration;
- include actual time-coded PNG frames extracted from the exact
  SHA-verified video master. Invented thumbnails do not satisfy this;
- still undergo **human listening and visual review** of pronunciation,
  transition timing, narration-to-caption sync, music mix/ducking, sound
  levels, soundtrack rights and the approved script/voice identity.

Stream timing and SRT syntax are only *technical controls*. They **cannot**
prove that individual spoken words align with subtitles, that voices sound
natural, or that the soundtrack was licensed. Signed current-script
recordings, independent creative review and exact-version founder/customer
approval remain mandatory separate gates. Keep CARSI silent previews and
Business Card films with unlicensed music in HOLD, regardless of technical
passes.

The suite includes negative controls for **missing audio**, a real
approximately **379 ms delayed AAC stream**, captions extending past the
film, and overlapping SRT captions. These must all be rejected.


## Profile-aware approval for websites and films

The independent reviewer found a P1: previously the generic release gate
required a 60-second film for every static website. This was a false HOLD,
not professional visual acceptance.

All release packets now declare deliverable_type explicitly: web or film.
For web, the SHA-bound candidate_artifact is a genuine PNG screenshot,
with the independent scope, mobile/tablet/desktop source audit, independent
creative reviews, prior baseline, comparison report and exact-candidate
founder approval. Video frames, audio, caption and film-only flags are NOT
required for a static web design. An invalid or missing deliverable_type
is HOLD. For film, the original full media decode, FFprobe timing,
exact frames, caption and sound rights are mandatory, and the film
SHA is bound to the same review and approval.

The evidence gate can verify files and the shape of approval records,
but CANNOT authenticate the alleged reviewer/owner identity or grant
commercial licensing. Those authority checks belong to independent
source-of-truth governance and are never inferred from synthetic fixtures.

The canonical Pi-Dev-Ops checkout includes the opt-in hook installation
source at scripts/install-sda-visual-hook.py, its tests at
scripts/test_install_sda_visual_hook.py, and the hook implementation in
hooks/sda_visual_router.py. Installation must use the reviewed release
process on each authorised host; the script refuses to overwrite existing
settings and is NOT a global automatic enrolment or a client approval.

## Exact creative approval scope binding (reviewer P2 repair, 1 November)

For any release profile the gate computes a deterministic SHA-256 digest of
the JSON object containing exactly these manifest fields:
`schema_version`, `deliverable_type`, `expected_pages`, `audit`,
`screenshots`, `candidate_artifact`, and `film` (including null/missing
fields as JSON null). The JSON is UTF-8, `sort_keys=True`, compact comma
and colon separators, and `ensure_ascii=False`. Consequently a changed
screen, page list, browser audit, master, caption file or inspection frame
changes the scope SHA, even if the hero screenshot is unchanged.

Both `reviews.sda.scope_sha256` and
`reviews.independent_challenger.scope_sha256`, the frozen
`comparison_report` JSON's `scope_sha256`, and
`founder_approval.scope_sha256` MUST match the newly computed exact scope
SHA. A prior approval cannot automatically carry over to a new screenshot
or media version. A stale/missing field forces HOLD. The original candidate
SHA and independent prior-baseline SHA remain separately checked.

This **binds recorded assertions to source bytes**, not to authenticated
identities. Client approval must still be checked by a tenant-aware server
against the signer and exact version, while media/licence and independent
creative acceptance require independent evidence. Do not treat these
manifest fields as a signature or automate acceptance on their presence.

Unsupported alternate A/V tracks, embedded subtitle streams or other
unverified streams are held rather than silently ignored. A genuine
multi-track delivery needs an independently reviewed verifier that checks
**every** released stream and source-aligned caption; deleting an
unverified stream is an editorial decision, not an automatic repair.

A full ecosystem rollout means merging reviewed canonical changes here
first, then updating the skills-library vendored pin to the exact merged
SHA, testing each host's installed copies, and maintaining client
approval as a separate authenticated operation.
