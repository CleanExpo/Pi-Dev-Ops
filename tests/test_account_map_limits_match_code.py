"""RA-8187: numeric limits stated in prose must equal the constants the code enforces.

Repeated kind (PR #990, rounds 7-9): ops/ACCOUNT-MAP.md and the validator's error messages
restated limits by hand ("8 digits", "at most 4 digits in all") and drifted from the code.
Messages now build from the constants in scripts/account_map_grammar.py; these tests fail if
a message or the doc names a number the constants do not hold.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import account_map_grammar as g  # noqa: E402

DOC = (ROOT / "ops" / "ACCOUNT-MAP.md").read_text(encoding="utf-8")
EXAMPLE_TICKET = "RA-8196"  # the one number-shaped example the messages may carry
SPELLED = {"two": 2, "three": 3, "four": 4}


def _numbers(text: str) -> list[int]:
    text = text.replace(EXAMPLE_TICKET, "")
    nums = [int(n) for n in re.findall(r"\d+", text)]
    return nums + [v for w, v in SPELLED.items() if re.search(rf"\b{w}\b", text)]


def _messages() -> list[str]:
    msgs = [g._email("bad value@x")[1], g._prose("x" * 500)[1], g._prose("1a")[1],
            g._prose("RA-1 RA-2 RA-3 RA-4")[1], g.check_comment("# " + "x" * 500)[1]]
    return msgs


def test_every_number_in_a_message_is_a_constant():
    allowed = {g.MAX_RUN, g.MAX_PROSE, g.MAX_TICKETS, g.MAX_DIGITS, g.MAX_MIXED,
               g.MAX_LOCAL, g.NUMBER_ONLY_MIN}
    for msg in _messages():
        stray = [n for n in _numbers(msg) if n not in allowed]
        assert not stray, f"message states numbers that are not constants: {stray} in {msg!r}"


def test_email_message_states_the_digit_cap_the_code_enforces():
    msg = g._email("bad value@x")[1]
    assert f"{g.MAX_DIGITS} digits" in msg and "8 digits" not in msg
    # and the code really rejects one digit over that cap
    over = "a" + "." .join("1" * 1 for _ in range(g.MAX_DIGITS + 1)) + "@example.com"
    assert g._email(over) is not None


def test_doc_digit_limits_equal_the_constants():
    flat = re.sub(r"\s+", " ", DOC)
    assert f"at most {g.MAX_DIGITS} digits in all" in flat
    assert f"({g.MAX_PROSE} characters max)" in flat
    assert f"at most {g.MAX_TICKETS} per line" in flat
    assert f"up to {g.DOMAIN_WORD} letters in an email domain ({g.MAX_RUN} in a name)" in flat
    assert f"may have at most {g.MAX_DIGITS} digits" in flat
    assert f"a {g.MAX_DIGITS}-digit PIN" in flat


def test_doc_ticket_digit_sentence_matches_ticket_pattern():
    flat = re.sub(r"\s+", " ", DOC)
    m = re.search(r"up to (\d+) digits, at most (\d+) per line", flat)
    assert m, "doc must state the ticket-id digit width and per-line cap"
    assert int(m.group(1)) == g.TICKET_DIGITS and int(m.group(2)) == g.MAX_TICKETS
    assert re.fullmatch(r"\(\?:RA\|UNI\|SYN\|AR\)-\[0-9\]\{1,%d\}" % g.TICKET_DIGITS, g._TICKET)
