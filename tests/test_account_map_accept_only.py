"""RA-8187 AR-01 accept-only redesign: every value must match its field's grammar.

Earlier rounds grew a deny-list one bypass at a time (W6 in the PR's "Five whys"). These
tests plant fake keys of each kind in every place a value can sit and assert the CLI (what
CI runs) exits 1. Keys are built by concatenation at test time and written to tmp_path, so
no key-shaped string is committed and the repo's own secret scanner stays quiet.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import account_map_grammar as grammar  # noqa: E402
import account_map_secrets as secrets  # noqa: E402
import check_account_map as cam  # noqa: E402

BASE = """\
# Account map test copy. Check it with scripts/check_account_map.py (RA-8187).
version: 1
machines:
  - id: mini
    host: Phills-Mac-mini
    notes: Always-on runner (RA-8187).
accounts:
  - label: claude-mini
    provider: claude
    plan: max
    email: claude-mini@pending.invalid
    machines: [mini]
    notes: Placeholder. Phill sets the real login.
"""

FAKE_KEYS = {
    "linear": "lin_api_" + "A1" * 20,
    "github": "ghp_" + "B2c3" * 9,
    "github_pat": "github_pat_" + "C3d4" * 10,
    "openai": "sk-" + "E5f6" * 12,
    "anthropic": "sk-ant-api03-" + "G7h8" * 10,
    "slack": "xoxb-" + "1234567890" + "-" + "abcdefghij",
}

# Each location turns a key into a full map text with the key planted there.
LOCATIONS = {
    "account_notes": lambda k: BASE.replace("Placeholder. Phill", f"Placeholder {k}. Phill"),
    "machine_notes": lambda k: BASE.replace("Always-on runner", f"Runner {k}"),
    "host": lambda k: BASE.replace("host: Phills-Mac-mini", f"host: {k}"),
    "label": lambda k: BASE.replace("label: claude-mini", f"label: {k}"),
    "email_local_part": lambda k: BASE.replace("claude-mini@", f"{k}@"),
    "plan": lambda k: BASE.replace("plan: max", f"plan: {k}"),
    "full_line_comment": lambda k: BASE + f"# old login {k}\n",
    "trailing_comment": lambda k: BASE.replace("version: 1", f"version: 1  # {k}"),
    "nested_notes": lambda k: BASE.replace(
        "notes: Placeholder. Phill sets the real login.", f"notes:\n      deep: {k}"),
    "nested_list": lambda k: BASE.replace("machines: [mini]", f"machines: [mini, [{k}]]"),
    "quoted_line_continuation": lambda k: BASE.replace(
        "notes: Placeholder. Phill sets the real login.",
        f'notes: "{k[:9]}\\\n      {k[9:]}"'),
}


def _run(tmp_path, text, capsys):
    path = tmp_path / "map.yaml"
    path.write_text(text, encoding="utf-8")
    code = cam.main(["--path", str(path)])
    return code, capsys.readouterr().out


def test_base_text_passes(tmp_path, capsys):
    """W4.5: the base map passes, so each failure below comes from its plant."""
    code, out = _run(tmp_path, BASE, capsys)
    assert code == 0, out


@pytest.mark.parametrize("location", sorted(LOCATIONS))
@pytest.mark.parametrize("kind", sorted(FAKE_KEYS))
def test_planted_key_fails(tmp_path, capsys, kind, location):
    """W6: a fake key of every kind, wherever it is planted, fails the build."""
    text = LOCATIONS[location](FAKE_KEYS[kind])
    assert FAKE_KEYS[kind][:9] in text or location == "quoted_line_continuation"
    code, out = _run(tmp_path, text, capsys)
    assert code == 1, out
    assert FAKE_KEYS[kind] not in out  # the validator never echoes the value


@pytest.mark.parametrize("kind", sorted(FAKE_KEYS))
def test_second_net_matches_every_fake_key_alone(kind):
    """W6: the second net alone recognises each kind, even glued to a word by '_'."""
    assert secrets.looks_secret_value(FAKE_KEYS[kind])
    assert secrets.looks_secret_value("x_" + FAKE_KEYS[kind])


def test_grammar_covers_every_key():
    """W6: accept-only means no schema field is free-form; a new field needs a grammar."""
    expected = ({("map", k) for k in cam.TOP_KEYS}
                | {("machine", k) for k in cam.MACHINE_KEYS}
                | {("account", k) for k in cam.ACCOUNT_KEYS})
    assert set(grammar.GRAMMAR) == expected


@pytest.mark.parametrize(
    "note",
    [
        "see https://linear.app/unite-group/issue/RA-8196",
        "login Hunter2pass here",
        "key=value",
        "mail me at someone@example.com",
        "x" * 25,
        "tab\there",
        "café login",
        "zero​width",
        "a" * 10 + " " + "b" * 10 + " " + "c " * 70,
    ],
)
def test_url_in_notes_or_mixed_word_fails_closed(note):
    """W6: notes accept short plain prose only; URLs, mixed words, odd characters fail."""
    assert grammar.GRAMMAR[("account", "notes")](note) is not None


@pytest.mark.parametrize(
    "note",
    ["", "Placeholder. Phill sets the real Claude login for the Mini.",
     "MacBook. Seat decision pending (RA-8196).", "Mac mini, always-on night-queue runner.",
     "Phill's old login; ask first?"],
)
def test_plain_prose_notes_pass(note):
    """W6: the grammar must not cry wolf on the notes Phill actually writes."""
    assert grammar.GRAMMAR[("account", "notes")](note) is None


def test_mixed_word_in_comment_fails(tmp_path, capsys):
    """W1.2: comments follow a word grammar too: letters-only or digits-only runs."""
    code, out = _run(tmp_path, BASE + "# login Hunter2pass\n", capsys)
    assert code == 1 and "BAD_VALUE" in out


def test_unknown_plan_fails_and_lists_choices():
    """W6: plan is a fixed choice; anything else fails and says what is allowed."""
    problem = grammar.GRAMMAR[("account", "plan")]("gold")
    assert problem is not None and "max" in problem[1]


def test_scanner_patterns_are_reused_not_copied():
    """W6: the second net loads app/server/scanner.py's own list, so the two cannot drift."""
    from app.server import scanner
    loaded = [p.pattern for p in secrets.scanner_patterns()]
    assert loaded == [entry[0] for entry in scanner._SECRET_PATTERNS]
    assert any("lin_api_" in p for p in loaded)


def test_missing_scanner_fails_closed(tmp_path, monkeypatch):
    """W5.5: if the scanner list cannot be read, the check errors rather than passing."""
    monkeypatch.setattr(secrets, "SCANNER_PATH", tmp_path / "absent.py")
    with pytest.raises(secrets.ScannerPatternsError):
        secrets.scanner_patterns()


def test_independent_second_net_only(tmp_path, capsys):
    """W6: a short Slack-shaped key is a valid slug, so the label grammar accepts it; the
    second net alone fires."""
    text = BASE.replace("label: claude-mini", "label: " + "xoxb-" + "12345-abcde")
    code, out = _run(tmp_path, text, capsys)
    assert code == 1 and "SECRET_VALUE" in out and "BAD_VALUE" not in out


def test_independent_grammar_only(tmp_path, capsys):
    """W6: a 26-letter run in notes is no known key shape; the grammar alone fires."""
    text = BASE.replace("Placeholder. Phill", "abcdefghijklmnopqrstuvwxyz Phill")
    code, out = _run(tmp_path, text, capsys)
    assert code == 1 and "BAD_VALUE" in out and "SECRET_VALUE" not in out


@pytest.mark.parametrize(
    "old, new",
    [
        ("version: 1", "version: true"),
        ("plan: max", "plan: !!binary aGVsbG8="),
        ("host: Phills-Mac-mini", "host: Phills_Mac_mini"),
        ("email: claude-mini@pending.invalid", "email: claude_mini@pending.invalid"),
    ],
)
def test_wrong_shapes_fail(tmp_path, capsys, old, new):
    """W4.1: booleans, binary tags and underscores are not accepted shapes."""
    code, out = _run(tmp_path, BASE.replace(old, new), capsys)
    assert code == 1, out


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
