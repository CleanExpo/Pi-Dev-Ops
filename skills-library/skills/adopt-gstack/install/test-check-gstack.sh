#!/usr/bin/env bash
# --check must go red when a denied Codex skill is present - including as a dangling symlink,
# which [ -e ] alone reports as absent. Fast: no install, needs the real pin checkout.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HOME/Developer/gstack-pinned"
[ -d "$SRC/.git" ] || { echo "SKIP: $SRC missing"; exit 0; }
T="$(mktemp -d "${TMPDIR:-/tmp}/gstack-check.XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/home/.claude/skills" "$T/home/.codex/skills" "$T/home/.gstack"
grep -v '^#' "$HERE/../allowlist.txt" | while read -r n; do mkdir -p "$T/home/.claude/skills/$n"; done
printf 'telemetry: off\nauto_upgrade: false\nproactive: false\n' > "$T/home/.gstack/config.yaml"
fail=0

check() { HOME="$T/home" CODEX_HOME="$T/home/.codex" GSTACK_SRC="$SRC" bash "${INSTALLER:-$HERE/install-gstack.sh}" --check >"$T/out" 2>&1; }

check; rc=$?
if [ "$rc" -eq 0 ]; then echo "PASS t0 clean home is green"; else echo "FAIL t0 clean home rc=$rc"; cat "$T/out"; fail=1; fi

ln -s "$T/missing-target" "$T/home/.codex/skills/gstack-land-and-deploy"
check; rc=$?
if [ "$rc" -ne 0 ] && grep -q "denied Codex skill present" "$T/out"; then echo "PASS t1 dangling denied link is red"
else echo "FAIL t1 dangling denied link not caught (rc=$rc)"; fail=1; fi

exit "$fail"
