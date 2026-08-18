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
# CI runs this as its own step in the `python` job; this runner did not, so a
# provisioning regression could pass here and only surface after the push.
if [ -f scripts/check_provisioning.py ]; then
  if [ "$PY_OK" = 1 ]; then
    gate "provisioning" "$PY" scripts/check_provisioning.py
  else skip "provisioning" "python deps absent"; fi
fi
# A declared-but-unresolvable business_charter degrades to charter_text="" in both
# discovery.py and workspace_context.py, so a session builds against an empty business
# brain and looks identical to a project that never declared one. Ratchet, not wall.
if [ -f scripts/check_business_charters.py ]; then
  if [ "$PY_OK" = 1 ]; then
    gate "business-charters" "$PY" scripts/check_business_charters.py
  else skip "business-charters" "python deps absent"; fi
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
#
# ruff's rule set changes between minor releases, so an unpinned local ruff makes this gate
# disagree with CI in BOTH directions. Observed 2026-08-18: a fresh venv picked up ruff
# 0.16.3, which reports 1006 errors across app/ — including UP017 on untouched code that is
# green on main — while ci.yml pins 0.15.10 and passes. The reverse is worse: an older local
# ruff goes green on code CI will reject, which is a gate that lies.
#
# ci.yml's pin is the single source of truth. Read it rather than hardcoding a second copy
# that would drift on the next bump, and fail loudly on mismatch instead of silently
# grading against the wrong rule set.
# Extraction is deliberately tolerant of quoting (pip install "ruff==X" / 'ruff==X' / ruff==X)
# and FAILS CLOSED when it cannot read a pin at all. An earlier draft guarded the comparison
# with [ -n "$RUFF_WANT" ], which meant any future reformatting of that ci.yml line silently
# disabled the whole check and restored the original defect — a guard that quietly stops
# guarding is worse than none, because the gate still reports PASS.
if command -v ruff >/dev/null 2>&1 && [ -d app ]; then
  RUFF_CI=".github/workflows/ci.yml"
  # Commented lines are dropped first: a stale '# pip install ruff==0.14.0' left above the real
  # step would otherwise win via head -1 and fail the gate against a version nobody installs.
  # `.*` between `pip install` and `ruff==` so flags survive (-U, --upgrade, other packages).
  # Without it `pip install -U "ruff==X"` extracted nothing, which fails closed — loud, but it
  # would break the gate on a legitimate ci.yml edit.
  RUFF_WANT="$(sed -n -e '/^[[:space:]]*#/d' -e "s/.*pip install.*ruff==[\"']\{0,1\}\([0-9][0-9.]*\)[\"']\{0,1\}.*/\1/p" "$RUFF_CI" 2>/dev/null | head -1)"
  RUFF_HAVE="$(ruff --version 2>/dev/null | awk '{print $2}')"
  # Reviewed 2026-08-18 for shell injection via these two values in the bash -c strings below,
  # and REFUTED BY EXECUTION, not by argument. The capture class is [0-9][0-9.]* so a crafted
  # pin `pip install "ruff==0.15.10' ; rm -rf / ; echo "` extracts exactly `0.15.10` — a quote
  # or semicolon cannot enter RUFF_WANT. RUFF_HAVE comes from the ruff binary's own output;
  # anyone able to control that already has code execution, so it is not an escalation.
  if [ -z "$RUFF_WANT" ] || [ -z "$RUFF_HAVE" ]; then
    gate "lint-ruff" bash -c "echo 'cannot determine the ruff version to grade against (ci.yml pin=\"$RUFF_WANT\", local=\"$RUFF_HAVE\").'; echo 'Refusing to lint rather than grade against an unknown rule set. Check the pip install ruff== line in $RUFF_CI'; exit 1"
  elif [ "$RUFF_WANT" != "$RUFF_HAVE" ]; then
    gate "lint-ruff" bash -c "echo 'ruff version drift: local $RUFF_HAVE, ci.yml pins $RUFF_WANT.'; echo 'This gate cannot stand in for CI on a different rule set. Fix: pip install \"ruff==$RUFF_WANT\"'; exit 1"
  else
    gate "lint-ruff" ruff check app
  fi
else skip "lint-ruff" "ruff not installed"; fi
if [ -f dashboard/package.json ]; then
  [ "$NODE_OK" = 1 ] && gate "lint-dashboard" bash -c 'cd dashboard && npm run --silent lint' \
    || { [ "$NODE_OK" = 1 ] || skip "lint-dashboard" "node_modules absent"; }
fi

# 6. Tests (skipped by --quick).
#
# test_sdk_phase2.py was excluded here as "needs claude_agent_sdk (CI-only)". That is not
# true: claude_agent_sdk is a declared dependency in app/requirements.txt, the file runs
# and passes locally, and CI does not exclude it. The exclusion made this gate strictly
# weaker than the CI job it is supposed to stand in for — the one situation a local gate
# must never be in, and worse while Actions is allocating no runners.
if [ "$MODE_QUICK" = 1 ]; then skip "tests" "--quick"
else
  if [ -d tests ]; then
    [ "$PY_OK" = 1 ] && gate "tests-python" "$PY" -m pytest tests/ -q \
      || { [ "$PY_OK" = 1 ] || skip "tests-python" "python deps absent"; }
  fi
  # CI runs `pytest swarm/` as its own step; this runner never did.
  if [ -d swarm ]; then
    [ "$PY_OK" = 1 ] && gate "tests-swarm" "$PY" -m pytest swarm/ -q \
      || { [ "$PY_OK" = 1 ] || skip "tests-swarm" "python deps absent"; }
  fi
  if [ -f dashboard/package.json ]; then
    [ "$NODE_OK" = 1 ] && gate "tests-dashboard" bash -c 'cd dashboard && CI=1 npm run --silent test' \
      || { [ "$NODE_OK" = 1 ] || skip "tests-dashboard" "node_modules absent"; }
  fi
fi

# 7. Production build (skipped by --quick).
#
# next.config.ts hard-fails the build when PI_CEO_URL / PI_CEO_PASSWORD are unset, so this
# gate failed on every run that did not happen to have them exported — and route-exercise
# below then failed too, having no build to serve. A permanently-red gate in the runner
# /session-handoff refuses to pass without is worse than no gate: it makes BLOCKED the
# normal verdict, so a real failure looks like the usual noise.
#
# These are the same build-time stubs ci.yml's `frontend` job sets. They are placeholders
# that satisfy a presence check during a static build, not credentials — nothing
# authenticates with them and no request is made at build time.
if [ "$MODE_QUICK" = 1 ]; then skip "build" "--quick"
elif [ -f dashboard/package.json ]; then
  [ "$NODE_OK" = 1 ] && gate "build-dashboard" env \
      PI_CEO_URL="http://127.0.0.1:7777" \
      PI_CEO_PASSWORD="placeholder-not-a-real-password" \
      NEXT_PUBLIC_SUPABASE_URL="https://stub.supabase.co" \
      NEXT_PUBLIC_SUPABASE_ANON_KEY="stub-key" \
      bash -c 'cd dashboard && npm run build' \
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
# audit-smoke — the repo's only end-to-end surface check (35 assertions across auth,
# sessions, lessons, webhook HMAC, rate limiting and autonomy status).
#
# It used to run only when a server HAPPENED to be listening on :7777. Nothing in this
# script, or any workflow, starts one — so it SKIPped on every run and the check has never
# actually executed here, while still reporting a tidy SKIP that reads like a considered
# decision. ci.yml's `smoke-local` job starts its own server for exactly this reason.
#
# Start one when the port is free, reuse a developer's server when it is not, and always
# clean up the process this script started.
_smoke_with_server() {
  local pw pid rc
  pw="ci-smoke-local-dummy-password"; pid=""
  if ! curl -sf -o /dev/null "http://127.0.0.1:7777/health" 2>/dev/null; then
    # TAO_CRON_ENABLED=0 is load-bearing, not tidiness. TAO_AUTONOMY_ENABLED
    # gates the Linear poller only; cron_loop is separate and, ten seconds
    # after boot, fires every trigger whose last_fired_at is older than its
    # schedule. Without this the gate runs a real board meeting (live model
    # calls) and real script triggers, and writes into .harness/ — a gate must
    # measure, not act. Observed doing exactly that before the flag existed.
    TAO_PASSWORD="$pw" TAO_SESSION_SECRET="ci-session-secret-fixed-for-test" \
    TAO_EVALUATOR_ENABLED=false TAO_SWARM_ENABLED=0 TAO_AUTONOMY_ENABLED=0 \
    TAO_CRON_ENABLED=0 \
    TAO_GC_MAX_AGE=3600 PYTHONPATH="$ROOT" \
      "$PY" -m uvicorn app.server.main:app --host 127.0.0.1 --port 7777 \
        --log-level warning >>"$LOG" 2>&1 &
    pid=$!
    # Trap armed IMMEDIATELY after the PID exists, before the readiness wait below.
    # It used to be installed after that loop, leaving a 30-second window in which
    # Ctrl-C leaked the uvicorn process — and a leaked server on :7777 is not a tidy
    # failure: the NEXT run sees a listener, treats it as "someone else's server",
    # and smoke-tests it with the wrong password, so the gate fails for a reason
    # unrelated to the code. Flagged by the gpt-oss-120b cross-model review.
    trap 'kill "$pid" 2>/dev/null; trap - INT TERM EXIT' INT TERM EXIT
    for _ in $(seq 1 30); do
      curl -sf -o /dev/null "http://127.0.0.1:7777/health" 2>/dev/null && break
      sleep 1
    done
  else
    # Someone else's server — use their password, and never kill it.
    pw="${TAO_PASSWORD:-dev}"
  fi
  "$PY" scripts/smoke_test.py --url http://127.0.0.1:7777 --password "$pw"
  rc=$?
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null
    trap - INT TERM EXIT
  fi
  return $rc
}
if [ "$PY_OK" = 1 ]; then
  gate "audit-smoke" _smoke_with_server
else skip "audit-smoke" "python deps absent"; fi

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
