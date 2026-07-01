#!/usr/bin/env bash
# handoff-loop.sh — the definition-of-done gate runner for /session-handoff.
#
# Runs the readiness gates for THIS repo, writes a timestamped healthcheck log to
# .handoff-logs/, and exits 0 only when every gate is green (or SKIPPED for a stated
# reason). /session-handoff runs this in Phase 0 and refuses to declare the tree ready
# until it exits 0; /resume-from-handoff re-runs it as its verification gate. Repo-
# adaptive: a gate is SKIPPED (not failed) when its stack is absent.
#
# Usage: scripts/handoff-loop.sh [--full] [--quick]
#   --full   real dependency install (npm ci / pip install) instead of presence-verify
#   --quick  skip the expensive build + test gates (fast interim handoff)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$ROOT/.handoff-logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/handoff-$TS.log"
MODE_FULL=0; MODE_QUICK=0
for a in "$@"; do
  [ "$a" = "--full" ] && MODE_FULL=1
  [ "$a" = "--quick" ] && MODE_QUICK=1
done

PASS=0; FAIL=0; SKIP=0
declare -a FAILED_GATES=()

log() { echo "$@" | tee -a "$LOG"; }

# gate <name> <command...> — run a gate, record PASS/FAIL, keep going.
gate() {
  local name="$1"; shift
  log ""; log "── GATE: $name"
  if "$@" >>"$LOG" 2>&1; then
    log "   PASS: $name"; PASS=$((PASS+1))
  else
    log "   FAIL: $name (rc=$?)"; FAIL=$((FAIL+1)); FAILED_GATES+=("$name")
  fi
}
skip() { log ""; log "── GATE: $1"; log "   SKIP: $1 — ${2:-not applicable to this repo}"; SKIP=$((SKIP+1)); }

log "handoff-loop $TS  root=$ROOT  full=$MODE_FULL quick=$MODE_QUICK"
log "branch=$(git branch --show-current 2>/dev/null)  head=$(git rev-parse --short HEAD 2>/dev/null)"

# 1. Cache / build bloat — light, source-safe clean.
gate "clean-bloat" bash -c '
  find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) \
    -not -path "*/node_modules/*" -prune -exec rm -rf {} + 2>/dev/null
  rm -rf dashboard/.next/cache 2>/dev/null; true'

# 2. Dependencies. Absent toolchain → SKIP (env not provisioned here), never FAIL.
PY_OK=0; NODE_OK=0
if [ -f app/requirements.txt ]; then
  [ "$MODE_FULL" = 1 ] && python3 -m pip install -q -r app/requirements.txt >>"$LOG" 2>&1
  if python3 -c "import fastapi, pydantic" >>"$LOG" 2>&1; then PY_OK=1; gate "deps-python" true
  else skip "deps-python" "app venv not active / deps not importable — run --full or activate the venv"; fi
fi
if [ -f dashboard/package.json ]; then
  [ "$MODE_FULL" = 1 ] && ( cd dashboard && npm ci >>"$LOG" 2>&1 )
  if [ -d dashboard/node_modules ]; then NODE_OK=1; gate "deps-node" true
  else skip "deps-node" "dashboard/node_modules absent — run with --full to install"; fi
fi

# 3. Generated files current — agentskills manifest must be a no-op re-run (needs PY).
if [ -f swarm/agentskills_manifest.py ]; then
  if [ "$PY_OK" = 1 ]; then
    gate "generated-agentskills" bash -c '
      python3 -m swarm.agentskills_manifest >/dev/null 2>&1
      git diff --quiet -- agentskills.json agentskills.yaml'
  else skip "generated-agentskills" "python deps absent"; fi
fi

# 4. Type checks.
if [ -f app/server/main.py ]; then
  [ "$PY_OK" = 1 ] && gate "type-python-import" python3 -c "from app.server.main import app" \
    || { [ "$PY_OK" = 1 ] || skip "type-python-import" "python deps absent"; }
fi
if [ -f dashboard/package.json ]; then
  [ "$NODE_OK" = 1 ] && gate "type-dashboard" bash -c 'cd dashboard && npx --no-install tsc --noEmit' \
    || { [ "$NODE_OK" = 1 ] || skip "type-dashboard" "node_modules absent"; }
fi

# 5. Lint.
if command -v ruff >/dev/null 2>&1 && [ -d app ]; then gate "lint-ruff" ruff check app
else skip "lint-ruff" "ruff not installed"; fi
if [ -f dashboard/package.json ]; then
  [ "$NODE_OK" = 1 ] && gate "lint-dashboard" bash -c 'cd dashboard && npm run --silent lint' \
    || { [ "$NODE_OK" = 1 ] || skip "lint-dashboard" "node_modules absent"; }
fi

# 6. Tests (skipped by --quick). test_sdk_phase2 needs claude_agent_sdk (CI-only) — excluded.
if [ "$MODE_QUICK" = 1 ]; then skip "tests" "--quick"
else
  if [ -d tests ]; then
    [ "$PY_OK" = 1 ] && gate "tests-python" python3 -m pytest tests/ -q --ignore=tests/test_sdk_phase2.py \
      || { [ "$PY_OK" = 1 ] || skip "tests-python" "python deps absent"; }
  fi
  if [ -f dashboard/package.json ]; then
    [ "$NODE_OK" = 1 ] && gate "tests-dashboard" bash -c 'cd dashboard && CI=1 npm run --silent test' \
      || { [ "$NODE_OK" = 1 ] || skip "tests-dashboard" "node_modules absent"; }
  fi
fi

# 7. Production build (skipped by --quick).
if [ "$MODE_QUICK" = 1 ]; then skip "build" "--quick"
elif [ -f dashboard/package.json ]; then
  [ "$NODE_OK" = 1 ] && gate "build-dashboard" bash -c 'cd dashboard && npm run build' \
    || { [ "$NODE_OK" = 1 ] || skip "build-dashboard" "node_modules absent — run --full"; }
fi

# 8. Audits.
if command -v detect-secrets >/dev/null 2>&1; then
  gate "audit-secrets" bash -c 'detect-secrets scan --all-files > /tmp/.ds-$$ 2>/dev/null; \
    ! grep -q "\"is_secret\": true" /tmp/.ds-$$; rm -f /tmp/.ds-$$'
else skip "audit-secrets" "detect-secrets not installed"; fi
if [ "$PY_OK" = 1 ] && curl -sf -o /dev/null "http://127.0.0.1:7777/health" 2>/dev/null; then
  gate "audit-smoke" python3 scripts/smoke_test.py --url http://127.0.0.1:7777 --password "${TAO_PASSWORD:-dev}"
else skip "audit-smoke" "python deps absent or local server not reachable on :7777"; fi

# Verdict.
log ""; log "════ SUMMARY  pass=$PASS fail=$FAIL skip=$SKIP"
if [ "$FAIL" -gt 0 ]; then
  log "════ VERDICT: BLOCKED — failing gates: ${FAILED_GATES[*]}"
  log "════ log: $LOG"; echo "$LOG"; exit 1
fi
if [ "$SKIP" -gt 0 ]; then
  log "════ VERDICT: READY (with $SKIP skipped — env not provisioned here; treat CI as source of truth for skipped gates)"
else
  log "════ VERDICT: READY — all $PASS gates green"
fi
log "════ log: $LOG"; echo "$LOG"; exit 0
