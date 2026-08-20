#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/aip-run-test.XXXXXX")"
trap 'rm -rf -- "${TMP_ROOT}"' EXIT

FAKE_BIN="${TMP_ROOT}/bin"
FAKE_HOME="${TMP_ROOT}/home"
FAKE_ENV="${FAKE_HOME}/.hermes/.env"
OP_CALLED="${TMP_ROOT}/op-called"
NPX_CALLED="${TMP_ROOT}/npx-called"
mkdir -p -- "${FAKE_BIN}" "$(dirname -- "${FAKE_ENV}")"

cat >"${FAKE_BIN}/op" <<'EOF'
#!/bin/sh
set -eu
: >"${OP_CALLED}"
if [ "${OP_MODE:-allow}" = "forbid" ]; then
  exit 91
fi
[ "${OP_SERVICE_ACCOUNT_TOKEN:-}" = "${EXPECTED_OP_TOKEN}" ] || exit 92
printf '%s' "${FAKE_SERVICE_KEY}"
EOF

cat >"${FAKE_BIN}/npx" <<'EOF'
#!/bin/sh
set -eu
[ "${SUPABASE_PICEO_SERVICE_KEY:-}" = "${FAKE_SERVICE_KEY}" ] || exit 93
[ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] || exit 94
: >"${NPX_CALLED}"
EOF
chmod 700 "${FAKE_BIN}/op" "${FAKE_BIN}/npx"

run_envless_wrapper() {
  env -i \
    PATH="${FAKE_BIN}:/usr/bin:/bin" \
    HOME="${FAKE_HOME}" \
    AIP_OP_SERVICE_ACCOUNT_ENV_FILE="${FAKE_ENV}" \
    EXPECTED_OP_TOKEN="test-headless-token" \
    FAKE_SERVICE_KEY="test-supabase-key" \
    OP_CALLED="${OP_CALLED}" \
    NPX_CALLED="${NPX_CALLED}" \
    "$@" \
    "${RUNNER}"
}

test_envless_gui_launch_uses_headless_token() {
  printf '%s\n' 'OP_SERVICE_ACCOUNT_TOKEN_NEXUS_AUDIT=test-headless-token' >"${FAKE_ENV}"
  chmod 600 "${FAKE_ENV}"
  rm -f -- "${OP_CALLED}" "${NPX_CALLED}"

  run_envless_wrapper

  [ -f "${OP_CALLED}" ]
  [ -f "${NPX_CALLED}" ]
}

test_missing_token_fails_before_op() {
  rm -f -- "${FAKE_ENV}" "${OP_CALLED}" "${NPX_CALLED}"

  if run_envless_wrapper OP_MODE=forbid >/dev/null 2>&1; then
    echo "expected missing-token launch to fail" >&2
    return 1
  fi

  [ ! -e "${OP_CALLED}" ] || {
    echo "op was called without a headless service-account token" >&2
    return 1
  }
  [ ! -e "${NPX_CALLED}" ]
}

test_envless_gui_launch_uses_headless_token
test_missing_token_fails_before_op
echo "AIP MCP wrapper token tests passed"
