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

# Interpreter. pyproject requires >=3.11, but a bare `python3` is 3.9 on some machines,
# where PEP-604 annotations (`str | None`, `Path | None`) raise TypeError at import time.
# That reads as broken code rather than a wrong interpreter, and has already produced one
# fully invalid gate run. Prefer the repo venv; where python3 is already >=3.11 this
# resolves to the same interpreter, so it is a no-op there. Exported so `bash -c` gates
# inherit it.
PY="python3"
if [ -d "$ROOT/.venv/bin" ]; then
  PY="$ROOT/.venv/bin/python3"
  # Also front the venv on PATH. $PY alone only fixes the gates' own interpreter — tests
  # spawn subprocesses that resolve `python3`/`pytest` from PATH and would still get 3.9,
  # and repo tools (ruff) live here too, which is why lint-ruff reported "not installed".
  # This is the `export PATH=…/.venv/bin:$PATH` workaround every caller was expected to
  # remember, moved into the script so forgetting it can no longer fake a verdict.
  PATH="$ROOT/.venv/bin:$PATH"; export PATH
fi
export PY

# 2. Dependencies. Absent toolchain → SKIP (env not provisioned here), never FAIL.
PY_OK=0; NODE_OK=0
if [ -f app/requirements.txt ]; then
  [ "$MODE_FULL" = 1 ] && "$PY" -m pip install -q -r app/requirements.txt >>"$LOG" 2>&1
  if "$PY" -c "import fastapi, pydantic" >>"$LOG" 2>&1; then PY_OK=1; gate "deps-python" true
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
      "$PY" -m swarm.agentskills_manifest >/dev/null 2>&1
      git diff --quiet -- agentskills.json agentskills.yaml'
  else skip "generated-agentskills" "python deps absent"; fi
fi
if [ -f scripts/check_agent_registry.py ]; then
  if [ "$PY_OK" = 1 ]; then
    gate "generated-agent-registry" "$PY" scripts/check_agent_registry.py
  else skip "generated-agent-registry" "python deps absent"; fi
fi

# 4. Type checks.
if [ -f app/server/main.py ]; then
  [ "$PY_OK" = 1 ] && gate "type-python-import" "$PY" -c "from app.server.main import app" \
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
    [ "$PY_OK" = 1 ] && gate "tests-python" "$PY" -m pytest tests/ -q --ignore=tests/test_sdk_phase2.py \
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

# 7b. Runtime route exercising (C12) — the authority on G1.
# Must follow build-dashboard: it serves the built output. The static check in the vitest
# suite is a TRIPWIRE over three literal spellings; this one starts the app and requests
# every internal link the pages actually rendered, so the form a link was written in stops
# mattering. Skipped under --quick and when there is no build to serve.
if [ "$MODE_QUICK" = 1 ]; then skip "route-exercise" "--quick"
elif [ -f dashboard/.next/BUILD_ID ]; then
  gate "route-exercise" node scripts/route-exercise.mjs
else skip "route-exercise" "no dashboard build to serve"; fi

# 8. Audits.
# Gate on the repo's own scanner — the same one CI blocks merges with (ci.yml "Secrets
# exposure scan"). --dry-run reports findings but never patches .gitignore, raises a
# Linear ticket or fires Telegram: a gate must measure, not act. Exit 0 clean / 1 on
# findings, both verified against a planted secret.
#
# This replaces a `detect-secrets scan` gate that was unable to fail three ways over:
#   1. detect-secrets was never installed, so it SKIPped permanently;
#   2. the body ended `rm -f /tmp/.ds-$$`, so bash -c returned rm's 0 and the `! grep`
#      verdict was computed and discarded;
#   3. it grepped for "is_secret", a field `scan` never emits — only `audit` writes it.
# Installing detect-secrets would therefore have turned an honest SKIP into a permanent
# green. Use the scanner that demonstrably works instead.
if [ -f scripts/secrets_check.py ]; then
  gate "audit-secrets" "$PY" scripts/secrets_check.py --repo-root "$ROOT" --dry-run
else skip "audit-secrets" "scripts/secrets_check.py not present"; fi
if [ "$PY_OK" = 1 ] && curl -sf -o /dev/null "http://127.0.0.1:7777/health" 2>/dev/null; then
  gate "audit-smoke" "$PY" scripts/smoke_test.py --url http://127.0.0.1:7777 --password "${TAO_PASSWORD:-dev}"
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
