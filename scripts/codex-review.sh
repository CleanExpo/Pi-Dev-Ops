#!/usr/bin/env bash
# codex-review.sh — run a cross-vendor review that can actually execute the suite.
#
# WHY THIS EXISTS
#
# Codex's Windows sandbox is a restricted-token sandbox ("windows unelevated
# restricted-token sandbox", per the binary's own strings). A restricted token cannot
# CreateProcess and cannot DELETE. Measured, not assumed — .harness/sandbox-probe/probe.cjs:
#
#   sandbox:  SPAWN_NET_USE FAIL EPERM | SPAWN_CMD FAIL EPERM | WRITE OK | UNLINK FAIL EPERM
#   control:  all OK
#
# That is fatal for a JS toolchain and explains both observed failures exactly:
#   - vitest dies because Vite's optimizeSafeRealPathSync() runs exec("net use") on Windows
#     on first realpath, and the throw lands OUTSIDE Vite's try/catch -> "failed to load config"
#   - next build dies on unlink('.next/app-path-routes-manifest.json') -- note WRITE was
#     permitted and only DELETE was denied, which is why it failed there and not earlier
#
# No tuning of that sandbox can run the suite: tests must spawn, builds must unlink.
# `[windows] sandbox` only selects elevated/unelevated. So review runs step outside it.
#
# WHAT REPLACES THE LOST ISOLATION
#
# Three controls, because "the brief says don't write code" is an instruction, not a control:
#   1. TREE INTEGRITY  - HEAD + full working-tree state hashed before and after. Any
#                        difference VOIDS the review. The reviewer reads; it does not write.
#   2. EXECUTION PROOF - the run FAILS if the transcript shows no evidence the suite ran.
#                        A reviewer that cannot execute cannot validate a verifier, so
#                        silent non-execution must be loud, not a footnote in the report.
#   3. PLAN AUTH       - refuses to run on a paid per-call key. Unchanged precondition.
#
# Usage: scripts/codex-review.sh <brief-path> <output-path>
set -uo pipefail

BRIEF="${1:?usage: codex-review.sh <brief-path> <output-path>}"
OUT="${2:?usage: codex-review.sh <brief-path> <output-path>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[ -f "$BRIEF" ] || { echo "FAIL: brief not found: $BRIEF"; exit 2; }

# ---- Control 3: plan auth, no paid fallback -------------------------------------
node -e '
const fs=require("fs"),os=require("os"),p=require("path");
const a=p.join(os.homedir(),".codex","auth.json");
if(!fs.existsSync(a)){console.error("no auth.json");process.exit(1)}
const d=JSON.parse(fs.readFileSync(a,"utf8"));
if(d.auth_mode!=="chatgpt"||d.OPENAI_API_KEY){console.error("auth_mode="+d.auth_mode+" key="+!!d.OPENAI_API_KEY);process.exit(1)}
' || { echo "FAIL: plan auth precondition not met — refusing to fall back to a paid API."; exit 2; }
echo "  precondition: plan auth OK"

# ---- Control 1 (pre): tree integrity --------------------------------------------
# Covers the SOURCE OF RECORD: tracked files, plus untracked files that are not ignored.
# Hashing `git status --porcelain` alongside HEAD catches an edit, a new file, a deletion,
# or a commit made mid-review.
#
# SCOPE LIMIT, STATED RATHER THAN IMPLIED: this is blind to gitignored paths. A file written
# to .next/, node_modules/, or any *.tmp is invisible here. That is deliberate and not
# fixable — the reviewer MUST write into those paths for the suite to run at all, so
# including them would void every legitimate run. The control's claim is "the reviewed
# artifact was not modified", NOT "the reviewer wrote nothing anywhere".
#
# Proven to discriminate (2026-08-01), because a control that cannot fail is not a control:
#   new non-ignored file -> DETECTED | edit to tracked file -> DETECTED | restored -> exact
#   pre-hash, no false positive. First two attempts at this control used a *.tmp path and
#   silently MISSED, which is how the scope limit above was found.
pre_head="$(git rev-parse HEAD)"
pre_tree="$(git status --porcelain | sort | sha256sum | cut -d' ' -f1)"

# ---- Control 1b (pre): the one machine-level path with teeth --------------------
# `-s danger-full-access` is MACHINE-wide; controls 1 and 2 are REPO-scoped. That asymmetry
# is real, so it gets a control rather than a caveat.
#
# ~/.codex/config.toml is the escalation path that matters: editing it is how a reviewer
# would permanently widen its OWN permissions for every future run — self-escalation, the
# shape R3 exists for, and the same family as a reviewer holding commit rights. Everything
# else outside the repo is either covered by `deploy_skills.py --check` or has no leverage.
CODEX_CFG="$HOME/.codex/config.toml"
pre_cfg="$( [ -f "$CODEX_CFG" ] && sha256sum "$CODEX_CFG" | cut -d' ' -f1 || echo MISSING )"
echo "  pre:  HEAD=${pre_head:0:8} tree=${pre_tree:0:12} codex-cfg=${pre_cfg:0:12}"

# ---- Run ------------------------------------------------------------------------
# -s danger-full-access: the sandbox cannot run the suite (see header). Deliberate,
# scoped to this invocation, never written into ~/.codex/config.toml.
# < /dev/null: codex exec reads stdin and hangs forever without it.
echo "  running reviewer (this takes a few minutes)..."
codex exec --skip-git-repo-check -s danger-full-access -m gpt-5.5 \
  "Read ${BRIEF//\//\\} and follow it exactly. It is the complete spec for this review.

You CAN execute commands in this environment — the sandbox restriction that blocked previous
rounds is lifted. RUN the loop the brief names and report what you actually observed. Do not
report test results you did not run. If a command fails, say so and paste the failure.

You are reviewing, not fixing. Do not edit, create or delete any file in the repository." \
  < /dev/null > "$OUT" 2>&1
rc=$?
echo "  reviewer exited rc=$rc, transcript: $OUT"

# ---- Control 1 (post): tree integrity -------------------------------------------
post_head="$(git rev-parse HEAD)"
post_tree="$(git status --porcelain | sort | sha256sum | cut -d' ' -f1)"
post_cfg="$( [ -f "$CODEX_CFG" ] && sha256sum "$CODEX_CFG" | cut -d' ' -f1 || echo MISSING )"
echo "  post: HEAD=${post_head:0:8} tree=${post_tree:0:12} codex-cfg=${post_cfg:0:12}"

VOID=0
if [ "$pre_head" != "$post_head" ] || [ "$pre_tree" != "$post_tree" ]; then
  echo ""
  echo "  ════ REVIEW VOID — the reviewer mutated the repository."
  echo "       A review that changed the thing it reviewed is not evidence about it."
  git status --porcelain | head -20
  VOID=1
fi

if [ "$pre_cfg" != "$post_cfg" ]; then
  echo ""
  echo "  ════ REVIEW VOID — ~/.codex/config.toml CHANGED DURING THE REVIEW."
  echo "       This is the self-escalation path: a reviewer widening its own permissions"
  echo "       for every future run. Treat as an incident, not a failed review."
  echo "       pre=$pre_cfg"
  echo "       post=$post_cfg"
  VOID=1
fi

# ---- Control 2: execution proof --------------------------------------------------
# Vitest prints "Tests  N passed" / "Test Files  N". Absence means the suite did not run,
# whatever the report claims about it.
if grep -qE "Tests +[0-9]+ (passed|failed)|Test Files +[0-9]+" "$OUT"; then
  echo "  execution proof: FOUND — the reviewer ran the suite"
else
  echo ""
  echo "  ════ NO EXECUTION PROOF — the transcript shows no suite run."
  echo "       Every 'green' in this report is the builder's claim, not the reviewer's."
  echo "       For a review OF A VERIFIER this is a hard fail: the claim under review is"
  echo "       'these checks fail red when they should', and only running them shows that."
  grep -iE "EPERM|spawn|sandbox|refus" "$OUT" | head -5
  VOID=1
fi

# ---- Verdict ---------------------------------------------------------------------
echo ""
if v=$(grep -m1 "^VERDICT" "$OUT"); then echo "  $v"; else echo "  NO VERDICT LINE — silence, timeout or crash is not a pass."; VOID=1; fi

[ "$VOID" -eq 0 ] || { echo ""; echo "  ════ RESULT: NOT USABLE AS EVIDENCE"; exit 1; }
echo "  ════ RESULT: usable — source of record unchanged, suite executed, verdict present"
echo "       (tree check does not cover gitignored paths — see Control 1 header)"
