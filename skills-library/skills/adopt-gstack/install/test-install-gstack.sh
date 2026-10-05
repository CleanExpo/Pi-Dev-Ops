#!/usr/bin/env bash
# Properties of install-gstack.sh, run in a throwaway HOME (never the real one):
#   1. idempotent: a second install succeeds after ./setup has rewritten tracked files
#   2. a local commit on the source checkout is still refused
# Slow (two full upstream setups). Needs bun and network.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/gstack-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/home/.claude/skills"
fail=0

run() { HOME="$T/home" CODEX_HOME="$T/home/.codex" GSTACK_SRC="$T/src" bash "${INSTALLER:-$HERE/install-gstack.sh}" >"$T/out" 2>&1; }

ref=()
[ -d "$HOME/Developer/gstack-pinned/.git" ] && ref=(--reference "$HOME/Developer/gstack-pinned")
git clone -q "${ref[@]}" https://github.com/garrytan/gstack.git "$T/src" || { echo "FAIL: clone"; exit 1; }

run; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL t1a: first install rc=$rc"; tail -5 "$T/out"; fail=1; }
dirty="$(git -C "$T/src" status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
echo "setup left $dirty modified tracked files"

run; rc=$?
if [ "$rc" -eq 0 ]; then echo "PASS t1 second install succeeds over setup-owned edits ($dirty files)"
else echo "FAIL t1 second install rc=$rc"; tail -5 "$T/out"; fail=1; fi

git -C "$T/src" -c user.email=t@t -c user.name=t commit -q --allow-empty -m "planted local commit"
run; rc=$?
if [ "$rc" -ne 0 ] && grep -q "local commits not on origin" "$T/out"; then echo "PASS t2 local commit refused"
else echo "FAIL t2 local commit not refused (rc=$rc)"; tail -5 "$T/out"; fail=1; fi

exit "$fail"
