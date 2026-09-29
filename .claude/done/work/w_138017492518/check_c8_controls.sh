#!/bin/bash
# Negative and positive controls for the v3 C8 recipe (review finding
# P1-DONE-C8-MASKED-VERIFIER-FAILURE). Runs the recipe text from contract.json verbatim, with a
# stand-in python3 first on PATH that ignores its arguments. Every line must start with "ok".
# Against the v2 recipe, cases 1, 2, 4 and 5 print WRONG.
cd "$(dirname "$0")/../../../.." || exit 9
CONTRACT=.claude/done/work/w_138017492518/contract.json
RECIPE=$(python3 -c "import json;print(json.load(open('$CONTRACT'))['criteria'][-1]['recipe'])")
HEAD_SHA=$(git rev-parse HEAD)
SHIM=$(mktemp -d)
fails=0
run_case() {  # name, expected(pass|fail), shim body
  printf '#!/bin/bash\n%s\n' "$3" > "$SHIM/python3"; chmod +x "$SHIM/python3"
  PATH="$SHIM:$PATH" bash -c "$RECIPE"; rc=$?
  if [ "$2" = pass ]; then [ $rc -eq 0 ] && v=ok || v=WRONG; else [ $rc -ne 0 ] && v=ok || v=WRONG; fi
  [ "$v" = ok ] || fails=$((fails + 1))
  echo "$v  $1 (expected $2, rc=$rc)"
}
run_case "marker inside a failing test line, exit 2" fail "echo 'running /usr/bin/false PR_RELEASE_GATE_PASS'; echo 'PR release gate BLOCKED: verification failed (1)' >&2; exit 2"
run_case "exact success line for HEAD but exit 2" fail "echo 'PR_RELEASE_GATE_PASS head=$HEAD_SHA reviewer=codex'; exit 2"
run_case "exit 0 with no output (exempt path)" fail "exit 0"
run_case "exit 0, success line for a different head" fail "echo 'PR_RELEASE_GATE_PASS head=0000000000000000000000000000000000000000 reviewer=codex'; exit 0"
run_case "exit 0, success line with trailing text" fail "echo 'PR_RELEASE_GATE_PASS head=$HEAD_SHA reviewer=codex extra'; exit 0"
run_case "POSITIVE: exit 0, exact success line for HEAD" pass "echo 'running x'; echo 'PR_RELEASE_GATE_PASS head=$HEAD_SHA reviewer=codex'; exit 0"
rm -rf "$SHIM"
exit $fails
