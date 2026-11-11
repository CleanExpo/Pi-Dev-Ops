"""RA-8187 AR-01 accept-only redesign: regressions for each independent review round.

Each section plants the exact shape a Codex review round found accepted (or echoed) and
asserts the CLI now exits 1 without printing it. Shared fixtures live in
test_account_map_accept_only.py; keys are built at test time, never committed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import account_map_grammar as grammar  # noqa: E402
import account_map_secrets as secrets  # noqa: E402
import check_account_map as cam  # noqa: E402
from test_account_map_accept_only import BASE, _run  # noqa: E402


# ── Review round 1 of the redesign (Codex, e021a2a7) ─────────────────────────

MIXED = "Ab1Cd2Ef3Gh4Ij5Kl6Mn" + "+" + "Op7Qr8St9Uv0Wx1Yz23"


@pytest.mark.parametrize("local", [MIXED, "Ab1Cd2Ef3Gh4", "a1b2c3d4"])
def test_high_entropy_email_local_part_fails(tmp_path, capsys, local):
    """W6.3: an email local part may end in a number (smith84) but not alternate letters
    and digits like a key does."""
    code, out = _run(tmp_path, BASE.replace("claude-mini@", f"{local}@"), capsys)
    assert code == 1 and "BAD_EMAIL" in out
    assert local not in out


@pytest.mark.parametrize("local", ["phill.mcgurk", "smith84", "ops+claude", "j-doe", "2024team"])
def test_ordinary_email_local_parts_pass(local):
    """W6.3: real addresses with a trailing or leading number still pass."""
    assert grammar.GRAMMAR[("account", "email")](f"{local}@gmail.com") is None


TOKENISH = "token-" + "Ab1Cd2Ef3Gh4" + "-" + "Ij5Kl6Mn7Op8"

ECHO_PLANTS = {
    "secret_named_key": lambda t: BASE.replace("    plan: max", f'    plan: max\n    "{t}": x'),
    "unknown_key": lambda t: BASE.replace("    plan: max", f"    plan: max\n    x{t[6:]}: x"),
    "nested_key": lambda t: BASE.replace(
        "notes: Placeholder. Phill sets the real login.", f"notes:\n      {t[6:]}: x"),
    "duplicate_key": lambda t: BASE.replace("    plan: max", f"    plan: max\n    k{t[6:]}: 1\n    k{t[6:]}: 2"),
    "label": lambda t: BASE.replace("label: claude-mini", "label: " + t[6:].lower()),
    "pin": lambda t: BASE.replace("machines: [mini]", "machines: [" + t[6:].lower() + "]"),
    "machine_id": lambda t: BASE.replace("id: mini", "id: " + t[6:].lower()),
}


@pytest.mark.parametrize("where", sorted(ECHO_PLANTS))
def test_refused_text_is_never_echoed(tmp_path, capsys, where):
    """W6.5: findings name the place and the rule, never the refused text."""
    code, out = _run(tmp_path, ECHO_PLANTS[where](TOKENISH), capsys)
    assert code == 1, out
    for piece in (TOKENISH, TOKENISH[6:], TOKENISH[6:].lower(), TOKENISH[6:26], TOKENISH[6:26].lower()):
        assert piece not in out, (where, out)


@pytest.mark.parametrize("field", [("account", "label"), ("machine", "id"), ("machine", "host")])
def test_key_like_slug_or_host_fails(field):
    """W6.3: slugs and hostnames may hold one letter/digit switch (mac2, claude-mini-2)
    but not the alternating mix of a key."""
    check = grammar.GRAMMAR[field]
    assert check("ab1cd2ef3gh4-ij5kl6mn7op8") is not None
    assert check("mac2") is None and check("claude-mini-2") is None


# ── Review round 2 of the redesign (Codex, 983caec3) ─────────────────────────

ANCHOR = "abcdefghijklmnopqrstuvwxyz" + "abcdef"


@pytest.mark.parametrize("comment", ["# p@ssword", "# Hunter2!", "# pass: x+y=z", "# " + "x" * 25])
def test_comment_outside_plain_prose_fails(tmp_path, capsys, comment):
    """W6.3: comments follow the same plain-word grammar as notes; punctuation such as
    @ + = and letter/digit mixes are refused."""
    code, out = _run(tmp_path, BASE + comment + "\n", capsys)
    assert code == 1 and "BAD_VALUE" in out


@pytest.mark.parametrize(
    "old, new",
    [
        ("email: claude-mini@", f"email: &{ANCHOR} claude-mini@"),
        ("plan: max", f"plan: &{ANCHOR} max\n    notes: *{ANCHOR}"),
        ("plan: max", "plan: !!str max"),
        ("plan: max", f"plan: !{ANCHOR} max"),
        ("version: 1", f"%YAML 1.1\n%TAG !{ANCHOR}! tag:x,2000:\n---\nversion: 1"),
    ],
)
def test_yaml_anchors_aliases_tags_and_directives_fail(tmp_path, capsys, old, new):
    """W6.5: anchors, aliases, tags and directives are YAML metadata the parser drops or
    hides; the map never needs them, so any of them fails and its name is not echoed."""
    code, out = _run(tmp_path, BASE.replace(old, new, 1), capsys)
    assert code == 1, out
    assert ANCHOR not in out


def test_committed_map_header_comments_pass():
    """W6.3: the real header comments still pass the stricter comment grammar."""
    text = cam.DEFAULT_PATH.read_text(encoding="utf-8")
    bad = [c for _, c in secrets.comment_lines(text) if grammar.check_comment(c)]
    assert bad == []


# ── Review round 3 of the redesign (Codex, 101b15ed) ─────────────────────────

CODE = "12" + "34" + "56"


@pytest.mark.parametrize(
    "old, new",
    [
        ("Placeholder. Phill", f"otp {CODE}. Phill"),
        ("version: 1", f"version: 1  # otp {CODE}"),
        ("version: 1", f"version: 1\n# recovery {CODE[:5]}"),
    ],
)
def test_login_code_length_number_fails(tmp_path, capsys, old, new):
    """W6.3: a standalone number in notes or comments is at most 4 digits (a year, a count);
    a 5-8 digit login or recovery code is refused, and not echoed."""
    code, out = _run(tmp_path, BASE.replace(old, new, 1), capsys)
    assert code == 1 and "BAD_VALUE" in out
    assert CODE[:5] not in out


def test_years_counts_and_ticket_ids_still_pass():
    """W6.3: ordinary numbers in prose keep working."""
    note = "Seat bought in 2026 for 3 people (RA-8196)."
    assert grammar.GRAMMAR[("account", "notes")](note) is None
    assert grammar.check_comment("# Since 2026, see RA-81960.") is None


def test_underscore_email_local_part_passes():
    """W4.4: underscores are common in real addresses; the run rules still apply."""
    assert grammar.GRAMMAR[("account", "email")]("phill_mcgurk@pending.invalid") is None
    assert grammar.GRAMMAR[("account", "email")]("x_Ab1Cd2Ef3@pending.invalid") is not None


def test_invalid_utf8_is_a_named_file_error(tmp_path, capsys):
    """W5.5: an unreadable file fails with rule FILE, not a traceback."""
    path = tmp_path / "map.yaml"
    path.write_bytes(BASE.encode() + b"\xff\n")
    assert cam.main(["--path", str(path)]) == 1
    assert "FILE" in capsys.readouterr().out


# ── Review round 4 of the redesign (Codex, 2d7d5e18) ─────────────────────────

LETTERS = "abcdefghijklmnopqrstuvwxyz" * 2


@pytest.mark.parametrize("length", [8, 24, 25, 32])
@pytest.mark.parametrize("where", ["unknown_key", "machine_id", "label", "pin"])
def test_long_letter_name_is_never_echoed(tmp_path, capsys, where, length):
    """W6.5, widened: no user-supplied name is printed at any length. A letters-only
    name cannot be told from a key by shape, so output uses positions, never names."""
    name = LETTERS[:length]
    plant = {
        "unknown_key": BASE.replace("    plan: max", f"    plan: max\n    {name}: x"),
        "machine_id": BASE.replace("id: mini", f"id: {name}"),
        "label": BASE.replace("label: claude-mini", f"label: {name}"),
        "pin": BASE.replace("machines: [mini]", f"machines: [{name}]"),
    }[where]
    path = tmp_path / "map.yaml"
    path.write_text(plant, encoding="utf-8")
    code = cam.main(["--path", str(path)])
    captured = capsys.readouterr()
    assert code == (0 if where == "label" and length == 8 else 1), captured.out
    assert name not in captured.out + captured.err, (where, captured.out)


# ── Review of the rebased head (Codex, 12d6a03b) ─────────────────────────────

NUMBER_ONLY = ["123456", "12345678", "12345", "123.456", "12-3456", "1_2_3_4_5"]


@pytest.mark.parametrize("domain", ["gmail.com", "pending.invalid"])
@pytest.mark.parametrize("local", NUMBER_ONLY)
def test_number_only_email_name_fails_and_is_not_echoed(tmp_path, capsys, local, domain):
    """W6.3: a login code can look like an email name. Five or more digits with no
    letters is refused as BAD_EMAIL and never printed, the same as a standalone
    6-digit number in notes (W5.2)."""
    code, out = _run(tmp_path, BASE.replace("claude-mini@pending.invalid", f"{local}@{domain}"), capsys)
    assert code == 1 and "BAD_EMAIL" in out, out
    assert local not in out and "123456" not in out


@pytest.mark.parametrize("local", ["1234", "2024", "007", "42", "1.2.3.4", "12-34", "123456team", "smith84"])
def test_short_or_lettered_number_email_names_pass(local):
    """W6.3: a number of up to 4 digits (a year or a count) stays allowed, matching the
    4-digit cap on standalone numbers in notes. A name that also holds letters is not
    number-only, and the letter and digit run rules already govern it."""
    assert grammar.GRAMMAR[("account", "email")](f"{local}@gmail.com") is None


# ── CodeRabbit round on PR 990 (five findings, kinds: grammar, loader, output, gate) ────

@pytest.mark.parametrize("domain", ["web3corp.com", "3m.com", "k12school.org", "my-web3.io"])
def test_real_domains_with_digits_pass(domain):
    """A domain label may mix letters and digits (at most two switches)."""
    assert grammar.GRAMMAR[("account", "email")](f"a@{domain}") is None


@pytest.mark.parametrize("domain", ["Ab1Cd2Ef3.com", "a1b2c3d4.com", "x" * 25 + ".com"])
def test_key_like_domain_labels_still_fail(domain):
    """The domain relaxation must not let a key-shaped label through."""
    assert grammar.GRAMMAR[("account", "email")](f"a@{domain}") is not None


@pytest.mark.parametrize("key", ["1", "true", "null", "2.5"])
def test_non_string_key_is_a_schema_error_not_a_duplicate(tmp_path, capsys, key):
    """1 and true are different YAML keys, so they are not DUPLICATE_KEY; a key that is
    not text is a SCHEMA error."""
    text = BASE + f"{key}: a\n" + ("true: b\n" if key == "1" else "")
    code, out = _run(tmp_path, text, capsys)
    assert code == 1 and "SCHEMA" in out and "DUPLICATE_KEY" not in out, out


def test_deeply_nested_yaml_reports_file_not_a_traceback(tmp_path, capsys):
    """A recursion failure in the loader is rule FILE, never a traceback."""
    code, out = _run(tmp_path, "[" * 5000 + "]" * 5000 + "\n", capsys)
    assert code == 1 and "FILE" in out and "Traceback" not in out, out


def test_summary_line_never_prints_a_credential_shaped_path(tmp_path, capsys):
    """The summary goes through the same filter as every finding."""
    from test_account_map_accept_only import FAKE_KEYS
    key = FAKE_KEYS["github"]
    path = tmp_path / f"{key}.yaml"
    path.write_text(BASE, encoding="utf-8")
    code = cam.main(["--path", str(path)])
    out = capsys.readouterr().out
    assert code == 0 and key not in out and "OK" in out, out


def test_missing_file_with_key_shaped_name_is_never_echoed(tmp_path, capsys):
    """The path is never printed: not in the summary, not in the FILE finding."""
    from test_account_map_accept_only import FAKE_KEYS
    name = "q" * 8 + "7" * 8 + "q" * 8   # letter, digit, letter run built at test time
    for text in (name, FAKE_KEYS["github"]):
        code = cam.main(["--path", str(tmp_path / f"{text}.yaml")])
        out = capsys.readouterr().out
        assert code == 1 and "FILE" in out and text not in out, out


@pytest.mark.parametrize("label", ["q" * 8 + "7" * 8 + "q" * 8, "q" * 13 + "7" * 3, "a1b2c3d4"])
def test_long_or_alternating_domain_label_is_refused(label):
    """The first-round domain relaxation let a 24-character letter/digit/letter label in."""
    assert grammar.GRAMMAR[("account", "email")](f"user@{label}.com") is not None
