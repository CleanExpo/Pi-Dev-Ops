"""Review round after the merge (CodeRabbit on 5b8d4c2a): ticket allow-list, digit codes, BOM."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import account_map_grammar as grammar  # noqa: E402
from test_account_map_accept_only import BASE, _run  # noqa: E402


@pytest.mark.parametrize("note", ["OTP-123456", "OTP-12345", "PIN-1234", "see OTP-123456 here"])
def test_credential_named_code_in_notes_is_refused(tmp_path, capsys, note):
    """Ticket ids are an allow-list of prefixes; OTP-123456 is not a ticket."""
    code, out = _run(tmp_path, BASE.replace("notes: Placeholder.", f"notes: {note}. Placeholder."), capsys)
    assert code == 1 and "BAD_VALUE" in out and "123456" not in out, out


@pytest.mark.parametrize("host", ["OTP-123456", "mini-123456", "a-12345"])
def test_digit_code_in_host_is_refused(tmp_path, capsys, host):
    code, out = _run(tmp_path, BASE.replace("host: Phills-Mac-mini", f"host: {host}"), capsys)
    assert code == 1 and "BAD_VALUE" in out and "123456" not in out, out


def test_real_ticket_ids_still_pass_in_notes():
    assert grammar.GRAMMAR[("account", "notes")]("Open decision RA-8196 and UNI-3306.") is None


def test_bom_before_header_comment_is_still_checked(tmp_path, capsys):
    """PyYAML skips a leading BOM, so the first line is a comment; it must be screened."""
    code, out = _run(tmp_path, "\ufeff# recovery 123456\n" + BASE, capsys)
    assert code == 1 and "123456" not in out, out
