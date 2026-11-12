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


def test_split_numeric_code_is_refused_in_notes_and_comments():
    """r6: a login code cut into several short groups must not pass as plain words."""
    code = "OTP " + "1" * 4 + " " + "2" * 4
    assert grammar.GRAMMAR[("account", "notes")](code + ".") is not None
    assert grammar.check_comment("# " + code) is not None


def test_ticket_ids_are_capped_per_line():
    many = " ".join(f"RA-{n}" for n in (1111, 2222, 3333, 4444))
    assert grammar.GRAMMAR[("account", "notes")](many) is not None
    assert grammar.check_comment("# " + many) is not None
    assert grammar.check_comment("# RA-1111 RA-2222 RA-3333") is None


@pytest.mark.parametrize("sep", ["\r", "\u2028", "\x0c"])
def test_odd_line_breaks_cannot_hide_a_comment(tmp_path, capsys, sep):
    code, out = _run(tmp_path, "# recovery OTP " + "1" * 4 + " " + "2" * 4 + sep + BASE, capsys)
    assert code == 1 and "1111" not in out, out


@pytest.mark.parametrize("field", [("machine", "host"), ("machine", "id"), ("account", "label"), ("account", "email")])
def test_split_numeric_code_is_refused_in_ids_and_hosts(field):
    """r7: two short digit groups must not pass as a slug, host or email; total digits are capped."""
    code = "otp-" + "1" * 4 + "-" + "2" * 4
    value = code + "@example.com" if field[1] == "email" else code
    check = grammar.GRAMMAR.get(field)
    assert check is not None and check(value) is not None


def test_ordinary_hosts_and_slugs_with_few_digits_still_pass():
    assert grammar.GRAMMAR[("account", "label")]("claude-mini-2") is None
    assert grammar.GRAMMAR[("machine", "host")]("Phills-Mac-mini") is None
