#!/usr/bin/env python3
"""strip_autogit_hooks.py removes autogit hooks and nothing else (RA-7802).

The Mini's settings.json carried autogit on PostToolUse, UserPromptSubmit and Stop,
each alone in its own entry, beside hooks that must survive untouched. These tests
plant exactly that shape. Stdlib only, no pytest.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strip_autogit_hooks import strip  # noqa: E402

AUTOGIT = {"hooks": [{"type": "command", "command": 'cd "${CLAUDE_PROJECT_DIR:-.}" && autogit ship || true'}]}
KEEP = {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 gate.py hook"}]}


def planted(tmp: Path) -> Path:
    p = tmp / "settings.json"
    p.write_text(json.dumps({"model": "x — y", "hooks": {
        "Stop": [KEEP, AUTOGIT], "PostToolUse": [AUTOGIT], "UserPromptSubmit": [AUTOGIT]}}))
    return p


def t1_removes_every_autogit_entry_and_keeps_the_rest() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = planted(Path(td))
        assert strip(p) == 3
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "autogit" not in p.read_text(encoding="utf-8")
        assert data["hooks"]["Stop"] == [KEEP]
        assert data["model"] == "x — y"          # other settings byte-for-byte, no \\u escapes
        assert "x — y" in p.read_text(encoding="utf-8")


def t2_backs_up_before_changing_and_leaves_a_clean_file_alone() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = planted(Path(td))
        before = p.read_text()
        strip(p)
        backups = list(Path(td).glob("settings.json.bak-autogit-*"))
        assert len(backups) == 1 and backups[0].read_text() == before
        after = p.read_text()
        assert strip(p) == 0 and p.read_text() == after          # idempotent
        assert len(list(Path(td).glob("settings.json.bak-autogit-*"))) == 1


def t3_a_missing_or_broken_file_is_left_alone() -> None:
    with tempfile.TemporaryDirectory() as td:
        assert strip(Path(td) / "absent.json") == 0
        bad = Path(td) / "bad.json"
        bad.write_text("{not json")
        assert strip(bad) == 0 and bad.read_text() == "{not json"


def t4_a_gate_sharing_an_entry_with_autogit_survives() -> None:
    """Cursor round 1: an entry was dropped whole if any hook in it mentioned
    autogit, disarming a real gate registered beside it."""
    gate = {"type": "command", "command": "python3 /hooks/real_enforcement_gate.py"}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "settings.json"
        p.write_text(json.dumps({"hooks": {"Stop": [
            {"matcher": "", "hooks": [gate, AUTOGIT["hooks"][0]]}]}}))
        assert strip(p) == 1
        assert json.loads(p.read_text(encoding="utf-8"))["hooks"]["Stop"] == [{"matcher": "", "hooks": [gate]}]


# The three autogit hooks from the Mac Mini's settings.json (backup of 28/09/2026), verbatim.
MINI_AUTOGIT = [
    'export PATH="/opt/homebrew/bin:$PATH"; cd "${CLAUDE_PROJECT_DIR:-.}" && command -v autogit >/dev/null 2>&1 && autogit busy || true',
    'cd "${CLAUDE_PROJECT_DIR:-.}" && command -v autogit >/dev/null 2>&1 && { case "$b" in main) ;; *) autogit ship ;; esac; } || true',
    "/usr/local/bin/autogit ship",
    # Quoted and nested spellings (Cursor round 4): none seen in the estate, but a miss here
    # leaves autogit committing and pushing, so these must be caught too.
    '"autogit" ship', "'autogit' ship", "`autogit` ship", 'sh -c "autogit ship"',
]
# Commands that merely CONTAIN the word, and must survive (Gemini cross-examination, 28/09).
NOT_AUTOGIT = ["/bin/check-autogit-status", "echo no-autogit-here", "python3 /hooks/no-autogit-guard.py",
               "python3 /hooks/autogit_audit.py"]


def t5_only_autogit_itself_is_removed() -> None:
    """A hook is autogit when autogit is the program it runs, not when the word
    appears inside another name. The real Mini commands are the positive control."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "settings.json"
        hooks = [{"type": "command", "command": c} for c in MINI_AUTOGIT + NOT_AUTOGIT]
        p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": hooks}]}}))
        assert strip(p) == len(MINI_AUTOGIT)
        left = [h["command"] for h in json.loads(p.read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"]]
        assert left == NOT_AUTOGIT, left


TESTS = (t1_removes_every_autogit_entry_and_keeps_the_rest,
         t2_backs_up_before_changing_and_leaves_a_clean_file_alone,
         t3_a_missing_or_broken_file_is_left_alone,
         t4_a_gate_sharing_an_entry_with_autogit_survives,
         t5_only_autogit_itself_is_removed)


def main() -> int:
    failures = []
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failures.append(t.__name__)
    n = len(TESTS)
    print(f"\n{n - len(failures)}/{n} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
