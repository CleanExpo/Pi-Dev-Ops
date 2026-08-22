"""Transactional rollback coverage for the Senior Harness installer."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "skills" / "senior-harness" / "scripts" / "install_senior_harness.sh"


def test_installer_restores_symlink_target_equal_to_old_sentinel(tmp_path: Path) -> None:
    stale = tmp_path / ".codex" / "skills" / "senior-harness"
    stale.parent.mkdir(parents=True)
    stale.symlink_to("__MISSING__")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_ln = fake_bin / "ln"
    fake_ln.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
count=0
[[ ! -f "$HARNESS_LN_COUNTER" ]] || count="$(<"$HARNESS_LN_COUNTER")"
count=$((count + 1))
printf '%s\n' "$count" > "$HARNESS_LN_COUNTER"
if [[ "$count" == "$HARNESS_LN_FAIL_AT" ]]; then exit 88; fi
exec /bin/ln "$@"
""",
        encoding="utf-8",
    )
    fake_ln.chmod(0o755)
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        PATH=f"{fake_bin}:{os.environ['PATH']}",
        HARNESS_LN_COUNTER=str(tmp_path / "ln-counter"),
        HARNESS_LN_FAIL_AT="2",
    )

    result = subprocess.run(
        ["bash", str(INSTALLER)],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 88
    assert "previous skill links were restored" in result.stderr
    assert stale.is_symlink()
    assert os.readlink(stale) == "__MISSING__"
