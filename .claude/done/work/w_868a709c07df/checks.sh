#!/bin/sh
# Done checks for RA-8379 (goal-ticket-form-async flake).
# Usage: checks.sh <repeat [n] | tsc | lint | suite | scope [base] | strict | mutant>
# Every check exits non-zero when it cannot run: an unavailable check is never a pass.
set -u

ROOT=$(cd "$(dirname "$0")/../../../.." && pwd) || exit 2
DASH="$ROOT/dashboard"
TEST="__tests__/goal-ticket-form-async.test.tsx"
WORK_DIR=".claude/done/work/w_868a709c07df"

# CI runs this suite on Node 20 (.github/workflows/ci.yml, frontend-tests).
NODE_BIN="${NODE20_BIN:-$HOME/.nvm/versions/node/v20.20.2/bin}"
[ -x "$NODE_BIN/node" ] || { echo "UNAVAILABLE: no Node 20 at $NODE_BIN"; exit 2; }
PATH="$NODE_BIN:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
export PATH
# Two checks parse Vitest output, so colour codes are switched off.
NO_COLOR=1
export NO_COLOR

need_deps() {
  [ -x "$DASH/node_modules/.bin/vitest" ] || { echo "UNAVAILABLE: dashboard dependencies are not installed"; exit 2; }
}

# The test file passes n fresh-process runs in a row (default 50).
repeat_runs() {
  need_deps
  n="${1:-50}"
  log=$(mktemp -t ra8379-repeat.XXXXXX) || exit 2
  cd "$DASH" || exit 2
  i=1
  while [ "$i" -le "$n" ]; do
    if ! npx vitest run "$TEST" >"$log" 2>&1; then
      echo "run $i of $n FAILED"
      tail -60 "$log"
      exit 1
    fi
    if ! grep -Eq 'Tests +[0-9]+ passed \([0-9]+\)' "$log"; then
      echo "run $i of $n reported no passed tests"
      tail -20 "$log"
      exit 1
    fi
    i=$((i + 1))
  done
  echo "$n of $n runs passed"
}

# Only the flake's own files (and this contract) changed since the merge base.
scope() {
  base="${1:-origin/main}"
  cd "$ROOT" || exit 2
  files=$(git diff --name-only "$base...HEAD") || exit 2
  [ -n "$files" ] || { echo "no changes against $base"; exit 1; }
  bad=0
  hit=0
  for f in $files; do
    case "$f" in
      dashboard/__tests__/goal-ticket-form-async.test.tsx) hit=1 ;;
      dashboard/lib/control/useGoalAnalysisJob.ts) hit=1 ;;
      dashboard/lib/control/goalAnalysisJob.ts) hit=1 ;;
      dashboard/components/control/GoalTicketForm.tsx) hit=1 ;;
      "$WORK_DIR"/*) ;;
      *) echo "out of scope: $f"; bad=1 ;;
    esac
  done
  [ "$hit" -eq 1 ] || { echo "no dashboard file changed"; exit 1; }
  exit "$bad"
}

# The test file still asserts the exact unreachable copy in all three places.
strict() {
  cd "$DASH" || exit 2
  count=$(grep -c 'toBe("Can.t reach the server, retrying")' "$TEST") || exit 1
  [ "$count" -ge 3 ] || { echo "only $count exact unreachable assertions remain"; exit 1; }
  echo "$count exact unreachable assertions"
}

# With the hook changed (in memory only) so a failed check keeps the old status,
# the quiet-fallback test must FAIL. Proves the fixed test can still go red.
mutant() {
  need_deps
  cd "$DASH" || exit 2
  dir="$DASH/node_modules/.cache/ra8379-mutant"
  mkdir -p "$dir" || exit 2
  marker="$dir/planted"
  echo no >"$marker"
  cat >"$dir/vitest.mutant.config.mts" <<EOF
import fs from "node:fs";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "$DASH",
  plugins: [
    {
      name: "ra8379-mutant",
      enforce: "pre",
      transform(code: string, id: string) {
        if (!id.split("?")[0].endsWith("/lib/control/useGoalAnalysisJob.ts")) return null;
        const out = code.replace("setJobLine(UNREACHABLE);", "void UNREACHABLE;");
        if (out === code) throw new Error("ra8379-mutant: nothing to mutate");
        fs.writeFileSync("$marker", "yes\n");
        return out;
      },
    },
    react(),
  ],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["$DASH/vitest.setup.ts"],
    testTimeout: 30_000,
    hookTimeout: 30_000,
    include: ["$TEST"],
  },
  resolve: { alias: { "@": "$DASH" } },
});
EOF
  log=$(mktemp -t ra8379-mutant.XXXXXX) || exit 2
  npx vitest run --config "$dir/vitest.mutant.config.mts" -t "never accepts a well-formed job" >"$log" 2>&1
  code=$?
  if [ "$(cat "$marker")" != "yes" ]; then
    echo "mutation was not planted"
    tail -30 "$log"
    exit 2
  fi
  if [ "$code" -eq 0 ]; then
    echo "the quiet-fallback test PASSED against the mutant: it cannot fail"
    tail -30 "$log"
    exit 1
  fi
  if ! grep -Eq 'FAIL .*never accepts a well-formed job' "$log"; then
    echo "vitest failed, but not on the quiet-fallback test"
    tail -40 "$log"
    exit 1
  fi
  echo "quiet-fallback test fails against the mutant, as required"
}

case "${1:-}" in
  repeat) repeat_runs "${2:-50}" ;;
  tsc) need_deps; cd "$DASH" || exit 2; npx tsc --noEmit ;;
  lint) need_deps; cd "$DASH" || exit 2; npm run lint ;;
  suite) need_deps; cd "$DASH" || exit 2; npm test ;;
  scope) scope "${2:-origin/main}" ;;
  strict) strict ;;
  mutant) mutant ;;
  *) echo "usage: checks.sh <repeat [n]|tsc|lint|suite|scope [base]|strict|mutant>"; exit 2 ;;
esac
