#!/usr/bin/env bash
# The ONLY place the codex challenge command line lives. Do not restate it elsewhere.
#
#   challenge.sh <round-dir> [design|code] [repo-path]
#
# Reads   <round-dir>/brief.md
# Writes  <round-dir>/report.json   (written by the codex CLI process, NOT the sandboxed
#                                    model — which is why --sandbox read-only works)
#         <round-dir>/run.log
# Prints  CLASS=<VERDICT|NO_VERDICT|QUOTA|CLASSIFIER_KILL|TIMEOUT> and exits 0 always;
#         the caller classifies, this script never decides a verdict.
set -uo pipefail

DIR="${1:?round-dir required}"
MODE="${2:-design}"
REPO="${3:-}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX="${CODEX_BIN:-$HOME/.local/bin/codex}"
LIMIT="${WATERLINE_TIMEOUT:-900}"
POLL="${WATERLINE_POLL:-5}"

# Both are env inputs to the loop that enforces "silence is not a pass", so a junk value
# must not disable it. Anything non-numeric or non-positive falls back to the default
# rather than producing a zero or negative budget — a timeout of 0 would kill every
# challenger instantly, which reads as a challenger that keeps dying.
# CLAMP, do not validate. Five review rounds were spent on this in its accept/reject
# form, each closing one hole and opening the next: an unbounded value overflowed the
# tick count, then bounding the inputs failed to bound their quotient, then a value
# textually below the floor was rounded up onto it by awk and admitted. Every one of
# those is the same shape — a boundary invites a value sitting just beside it, and
# deciding which side it falls on is a judgement that can always be wrong.
#
# Clamping has no such boundary. Nothing is accepted or rejected; every input, however
# absurd, is MAPPED into the usable range, and the resolved value is what the BUDGET line
# reports. Non-numeric text becomes 0 in awk and therefore clamps to the floor.
# An in-range value is echoed BYTE-IDENTICALLY rather than reformatted. Printing it back
# through "%g" cost six significant figures — 1.000001 came out as 1, so the budget was
# shorter than the configured timeout, which is the spurious-TIMEOUT path all over again.
# Only a value that actually needs changing is replaced, and then by a literal bound.
clamp() {   # value lo hi default
  awk -v v="$1" -v lo="$2" -v hi="$3" -v d="$4" 'BEGIN{
    if (v !~ /^[0-9]*\.?[0-9]+$/) { print d; exit }
    if (v+0 < lo) { print lo; exit }
    if (v+0 > hi) { print hi; exit }
    print v
  }'
}
LIMIT="$(clamp "$LIMIT" 0.001 604800 900)"   # 1ms .. 7 days
POLL="$(clamp "$POLL"  0.001 3600   5)"      # 1ms .. 1 hour
# Budget in POLL-sized ticks. Counting ticks rather than reading the shell's SECONDS
# keeps sub-second polling honest: SECONDS has one-second granularity and can advance
# immediately after the loop starts, which timed out a 100ms challenger roughly one run
# in ten.
#
# CONTRACT, for any ACCEPTED limit (see the range check above; a rejected one becomes the
# default): the effective budget is whole ticks and never fewer than one, so it is
# LIMIT rounded UP to a tick boundary. Never down. Flooring looked harmless and was not:
# LIMIT=2.9 with POLL=1 gave two ticks, timing a challenger out 0.9s EARLY. The error
# must always run toward granting more time, because a budget shorter than the
# configured one can only produce a spurious TIMEOUT — and since the caller retries on
# TIMEOUT, a round that was never allowed to run is indistinguishable from one that
# found nothing.
MAX_TICKS="$(awk -v l="$LIMIT" -v p="$POLL" \
  'BEGIN{n=l/p; printf "%d", (n<=1 ? 1 : (n==int(n) ? n : int(n)+1))}')"

# The POLL floor is what keeps this representable, and it is the reason the floor exists
# at all: bounding LIMIT and POLL individually does not bound their QUOTIENT. Without it,
# the smallest POLL the regex admits wanted 6e20 ticks for a 7-day limit, printf "%d"
# capped that at INT64_MAX, and the budget came out at 9223s instead of 604800 — the same
# overflow as the round-11 finding, one door along. At the worst admissible corner
# (604800 / 0.001) the count is 6.048e8, nine orders inside INT64_MAX and exact in a
# double. t9f pins that corner so the bound cannot be widened without the test saying so.

# Announce the budget the round actually got, on stderr, where it joins the caller's log.
# Two of these values may differ from what the environment asked for, and a silently
# substituted default is the kind of thing you want in the record before a round goes
# wrong rather than after. It is also the only way to test the resolution itself: every
# out-of-range LIMIT is effectively infinite, so no timing observation can distinguish
# a correct budget from a broken one.
printf 'BUDGET limit=%s poll=%s ticks=%s\n' "$LIMIT" "$POLL" "$MAX_TICKS" >&2

[ -r "$DIR/brief.md" ] || { echo "CLASS=NO_VERDICT reason=no-brief"; exit 0; }

# Design briefs run in a scratch dir with the user config dropped, so the challenger does
# not inherit ~/.codex/AGENTS.md ("Claude Code receives the same shared context on this
# workstation") or the same second-brain MCP corpus the author already read. Code-shaped
# briefs need the repo, and therefore DO inherit its AGENTS.md — the caller records that.
if [ "$MODE" = "code" ]; then
  CWD="${REPO:?repo-path required for code mode}"; ISOLATE=()
else
  CWD="$DIR"; ISOLATE=(--ignore-user-config)
fi

# Probe by executing, never by trusting a documented list. gpt-5.3-codex and
# gpt-5.6-terra-pro hard-fail 400 on a ChatGPT-plan account.
for MODEL in gpt-5.6-terra gpt-5.6-luna gpt-5.6-sol; do
  : > "$DIR/run.log"; rm -f "$DIR/report.json"

  "$CODEX" exec \
    --sandbox read-only \
    --skip-git-repo-check \
    "${ISOLATE[@]}" \
    -C "$CWD" \
    -m "$MODEL" \
    -c model_reasoning_effort=high \
    --output-schema "$SKILL_DIR/references/challenge-schema.json" \
    --output-last-message "$DIR/report.json" \
    - < "$DIR/brief.md" > "$DIR/run.log" 2>&1 &
  PID=$!

  # The poll tick is a floor on every invocation, and at a fixed 5s the test suite grew
  # slow enough that an independent reviewer could not finish a gate run inside its own
  # command timeout. A review that cannot run the suite is not a review — hence a
  # tunable, fractional POLL.
  # Sleep BEFORE counting the tick: a budget of one tick has to permit one interval.
  # Counting first killed a healthy 100ms challenger outright whenever TIMEOUT <= POLL,
  # and a spurious TIMEOUT is a false clean by another route, since the caller retries.
  TICKS=0
  while kill -0 "$PID" 2>/dev/null; do
    sleep "$POLL"
    TICKS=$((TICKS + 1))
    if [ "$TICKS" -ge "$MAX_TICKS" ] && kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
      WAITED="$(awk -v t="$TICKS" -v p="$POLL" 'BEGIN{printf "%g", t*p}')"
      echo "CLASS=TIMEOUT model=$MODEL waited=${WAITED}s"; exit 0
    fi
  done
  wait "$PID"; RC=$?

  # A 400 on this model means the plan does not serve it — fall through to the next.
  if grep -qiE '400|unsupported model|model_not_found' "$DIR/run.log" \
     && ! [ -s "$DIR/report.json" ]; then continue; fi

  if grep -qiE '429|rate limit|quota|usage limit' "$DIR/run.log"; then
    echo "CLASS=QUOTA model=$MODEL"; exit 0; fi

  # Classify the FAILURE first. A run that crashed cannot clear anything, however
  # well-formed the JSON it left behind — rule 3, silence/timeout/crash is not a pass.
  # This check used to sit below the verdict branch, so a 400 that still wrote a file
  # was cleared as VERDICT.
  # The partial log has twice held a real defect — the caller MUST read it before retrying.
  [ "$RC" -ne 0 ] && { echo "CLASS=CLASSIFIER_KILL model=$MODEL rc=$RC log=$DIR/run.log"; exit 0; }

  # Parseable is not valid, and neither is key-present. `{}` decodes; so does a payload
  # carrying all six keys with `verdict: "NOT-A-VERDICT"` and `blocking_findings: {}`.
  # Both mint the zero-findings clearance this gate exists to withhold, so the FULL
  # schema is enforced, once, in validate_report.py against the schema file itself.
  # The validator's detail quotes key names the challenger chose. It is written to a file
  # and NEVER interpolated into the line below: this script's contract with its caller is
  # one CLASS= line, and text that reaches it can forge one. A newline once appended a
  # second `CLASS=VERDICT`; stripping newlines then left `CLASS=VERDICT` sitting inside
  # the reason for a token grep to find. Every field on the line is now a value this
  # script chose.
  VALID=1
  if [ -s "$DIR/report.json" ]; then
    python3 "$SKILL_DIR/scripts/validate_report.py" "$DIR/report.json" \
      2> "$DIR/validate.log" && VALID=0
  fi

  [ "$VALID" -eq 0 ] && { echo "CLASS=VERDICT model=$MODEL"; exit 0; }
  echo "CLASS=NO_VERDICT model=$MODEL reason=invalid-report detail=$DIR/validate.log"
  exit 0
done

echo "CLASS=NO_VERDICT reason=no-model-served-by-plan"; exit 0
