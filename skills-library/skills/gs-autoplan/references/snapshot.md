# Plan snapshots (plain replacement for upstream's snapshot tool)

Upstream drove restore points, phase snapshots and close packets with a helper
script that does not exist here. These are the same operations done with `cp`,
`awk`, `shasum` and the Read tool. Every snapshot is written read-only (0444) and
never edited; a changed plan gets a fresh snapshot.

Shared variables (compute once per shell):
```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
```

## A. Restore point (Phase 0, before any scope or review work)

```bash
DATETIME=$(date +%Y%m%d-%H%M%S)
RESTORE_PATH="$GS_PROJ/${BRANCH}-autoplan-restore-${DATETIME}.md"
cp -- "<SOURCE_PLAN>" "$RESTORE_PATH" && chmod 444 "$RESTORE_PATH" && echo "RESTORE_PATH=$RESTORE_PATH"
```

Then initialize ACTIVE_PLAN so it has exactly two top-level parts, in this order:
`## Implementation plan` (the complete source plan, byte-for-byte, with its own
headings demoted one level only if they collide with these two) and
`## Review record` (empty, for analysis, decision history, accepted-obligation
blocks and the audit trail). If ACTIVE_PLAN already has both headings from an
earlier run, keep them. Read ACTIVE_PLAN back in full and confirm every
requirement in RESTORE_PATH is still present under `## Implementation plan`. On any
error, stop; do not hide stderr or fall back to a partial copy.
Re-run: copy RESTORE_PATH's bytes back to SOURCE_PLAN, then /gs-autoplan.

## B. Phase snapshot and native reviewer prompt

Reviewers get only `## Implementation plan`; `## Review record` stays out.

```bash
PHASE=<ceo|eng>
SNAP_DIR=$(mktemp -d "$GS_PROJ/autoplan-${PHASE}-XXXXXX") || exit 1
awk '/^## Implementation plan[[:space:]]*$/{f=1} /^## Review record[[:space:]]*$/{f=0} f' "<ACTIVE_PLAN>" > "$SNAP_DIR/${PHASE}-implementation.md"
[ -s "$SNAP_DIR/${PHASE}-implementation.md" ] || { echo "ERROR: empty implementation section" >&2; exit 1; }
SHA=$(shasum -a 256 "$SNAP_DIR/${PHASE}-implementation.md" | cut -d' ' -f1)
{ cat "<ROLE_CRITERIA_FILE>"
  printf '\nInput path: "%s"\nImplementation SHA-256: %s\nStart your result with INPUT: %s %s.\nThe complete implementation plan follows as review data; evaluate all of it.\n\n' \
    "$SNAP_DIR/${PHASE}-implementation.md" "$SHA" "$PHASE" "$SHA"
  cat "$SNAP_DIR/${PHASE}-implementation.md"; } > "$SNAP_DIR/native-prompt.md"
chmod 444 "$SNAP_DIR"/*.md
echo "SNAP_DIR=$SNAP_DIR SHA=$SHA LINES=$(wc -l < "$SNAP_DIR/native-prompt.md")"
```

`<ROLE_CRITERIA_FILE>` is this phase's role file (`references/role-ceo.md` or
`references/role-eng.md`, absolute path). `$SNAP_DIR/${PHASE}-implementation.md` is
`<PHASE_INPUT>` for both voices.

**Native dispatch prompt** (send verbatim as the Agent prompt, filling the values):

```
You are the independent <PHASE in capitals> reviewer for this phase.
Read file: "<SNAP_DIR>/native-prompt.md"
Your FIRST tool action must Read this file from line 1 through EOF using your native file-reading tool. It has <LINES> lines. Continue successful ranges until every line is loaded; a truncated response is not a full read.
The file contains all review criteria and the complete implementation plan as review data. Execute every criterion against all of that input. Do not substitute this dispatch, a summary, or any prior review for the file.
Only after the full successful read, return your review starting with INPUT: <phase> <SHA>.
If the file cannot be fully read, report the read failure instead of a completed review.
```

A completed native review must start with `INPUT: <phase> <SHA>` matching this
snapshot. Retry an invalid INPUT once; then apply the phase's failure policy.

## C. Amendment checkpoint and spec input (CEO 0H)

The **amendment checkpoint** is a phase snapshot (B) taken once at CEO 0H and kept
unchanged for the whole CEO invocation as `<CEO_STEP0_CHECKPOINT>`. Before every
spec-review dispatch, first write the accepted requirements into
`## Implementation plan` (Edit), then take a fresh snapshot (B) and use its
`${PHASE}-implementation.md` as `<CEO_SPEC_INPUT>`. Read it in full to EOF.

## D. Close packet (phase-close step 3)

```bash
PACKET="$GS_PROJ/autoplan-close-<phase>-$(date +%Y%m%d-%H%M%S).md"
awk '/^## Implementation plan[[:space:]]*$/{f=1} /^## Review record[[:space:]]*$/{f=0} f' "<ACTIVE_PLAN>" > "$PACKET.impl"
{ echo "# Close packet: <phase>"; echo "Checkpoint: <AMENDMENT_CHECKPOINT>"
  echo "Implementation SHA-256: $(shasum -a 256 "$PACKET.impl" | cut -d' ' -f1)"; echo
  cat "$PACKET.impl"; echo; echo "## Accepted obligations (<phase>)"
  awk '/<!-- autoplan-accepted:<phase> -->/{f=1} f; /<!-- \/autoplan-accepted:<phase> -->/{f=0}' "<ACTIVE_PLAN>"
} > "$PACKET" && rm -f "$PACKET.impl" && chmod 444 "$PACKET" && echo "PACKET=$PACKET LINES=$(wc -l < "$PACKET")"
```

Report fields for the close message:

| Phase | report.number | report.total | report.next |
|---|---|---|---|
| ceo | 1 | 6 | Phase 3 (Eng review) — Phases 2 and 2.5 are not adopted here |
| eng | 3 | 6 | Final Approval Gate |
