"""Accept-only value grammar for the account map (RA-8187).

Every key the schema allows has exactly one entry in GRAMMAR. A value passes only when it
matches its field's shape: an email, a fixed choice, a short slug or hostname, short plain
prose, or null where a field is still undecided. Anything else fails closed. This replaces
the earlier approach of listing "known bad" text, which missed a new shape each round.

Each check returns None when the value is accepted, or (rule, reason). A reason never
quotes the value, so a pasted credential is not echoed into CI logs.
"""
from __future__ import annotations

import re

PROVIDERS = ("claude", "codex", "cursor")
PLANS = ("free", "plus", "pro", "max", "max-5x", "max-20x", "team", "business",
         "enterprise", "ultra", "chatgpt-plus", "chatgpt-pro")
SCHEMA_VERSION = 1

_SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_HOST = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")
_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9]+(?:[._+-][A-Za-z0-9]+)*")
_EMAIL_DOMAIN = re.compile(r"(?:[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\.)+[A-Za-z]{2,24}")
_PROSE_CHARS = re.compile(r"[A-Za-z0-9 ,.;:()'/?!-]*")
_PROSE_WORD = re.compile(r"[A-Z]{2,6}-[0-9]{1,6}|[0-9]{1,4}|[A-Za-z]+(?:['/-][A-Za-z]+)*")
# Comments may also name files (scripts/check_account_map.py, ops/ACCOUNT-MAP.md).
_COMMENT_CHARS = re.compile(r"[A-Za-z0-9 ,.;:()'\"/?!_-]*")
_COMMENT_WORD = re.compile(r"[A-Z]{2,6}-[0-9]{1,6}|[0-9]{1,4}|[A-Za-z]+(?:[-_./'][A-Za-z]+)*")
_ALNUM_RUN = re.compile(r"[A-Za-z0-9]+")
_MIXED = re.compile(r"[A-Za-z]")
_ONE_SWITCH = re.compile(r"[A-Za-z]+[0-9]+|[0-9]+[A-Za-z]+")
_SHOWABLE = re.compile(r"[A-Za-z_]+(?:-[A-Za-z_]+)*(?:-[0-9]{1,4})?")

MAX_RUN = 24      # longest unbroken run of letters or digits anywhere (a word, a label)
MAX_PROSE = 160   # notes are one short line


def _runs_ok(text: str, limit: int = MAX_RUN, one_switch: bool = False) -> bool:
    """Every run of letters/digits is short and is letters-only or digits-only. With
    one_switch (emails), a run may switch once, as in smith84 or 2024team, but never
    alternate the way a key does (Ab1Cd2)."""
    for run in _ALNUM_RUN.findall(text):
        mixed = _MIXED.search(run) and any(c.isdigit() for c in run)
        if len(run) > limit or (mixed and not (one_switch and _ONE_SWITCH.fullmatch(run))):
            return False
    return True


def show(name) -> str:
    """A name safe to print: plain words with an optional short number. Anything else
    could be pasted text, so findings name the place and the rule, never the text. A run
    longer than the grammar's word limit is hidden too: nothing is printed that the field
    grammar itself would refuse for length."""
    if (isinstance(name, str) and len(name) <= 32 and _SHOWABLE.fullmatch(name)
            and _runs_ok(name)):
        return f"'{name}'"
    return "(name not shown)"


def _text(check):
    """Wrap a string check: non-strings are a SCHEMA error."""
    def wrapped(value):
        if not isinstance(value, str):
            return ("SCHEMA", f"must be text, got {type(value).__name__}")
        return check(value)
    return wrapped


def _nullable(check):
    """null means "not decided yet" and is accepted; anything else goes to check."""
    return lambda value: None if value is None else check(value)


def _bounded(pattern, max_len: int, what: str, rule: str = "BAD_VALUE", max_seg: int = 16):
    def check(value: str):
        segments = re.split(r"[.+-]", value)
        if (len(value) > max_len or not pattern.fullmatch(value)
                or any(len(s) > max_seg for s in segments) or not _runs_ok(value, one_switch=True)):
            return (rule, f"must be {what}")
        return None
    return _text(check)


def _email(value):
    if not isinstance(value, str):
        return ("BAD_EMAIL", f"must be one plain address, got {type(value).__name__}")
    local, at, domain = value.partition("@")
    if (not at or len(value) > 80 or len(local) > 40 or not _EMAIL_LOCAL.fullmatch(local)
            or not _EMAIL_DOMAIN.fullmatch(domain)
            or not _runs_ok(value, one_switch=True)):
        return ("BAD_EMAIL", "must be one plain address (letters, digits, '.', '_', '+', '-'; "
                "local part at most 40 characters; no key-like mix of letters and digits)")
    return None


def _prose(value: str):
    if len(value) > MAX_PROSE or not _PROSE_CHARS.fullmatch(value):
        return ("BAD_VALUE", f"must be one line of plain prose, at most {MAX_PROSE} "
                "characters, letters, digits and . , ; : ( ) ' / ? ! - only")
    for word in value.split(" "):
        word = word.strip("(\"'").rstrip(",.;:)'\"?!")
        if word and (len(word) > MAX_RUN or not _PROSE_WORD.fullmatch(word)):
            return ("BAD_VALUE", "each word must be letters, a number of up to 4 digits or a ticket id "
                    "like RA-8196, at most 24 characters (no links, codes or mixed words)")
    return None


def _choice(options: tuple, rule: str = "BAD_VALUE"):
    def check(value):
        if not isinstance(value, str):
            return ("SCHEMA", f"must be text, got {type(value).__name__}")
        if value not in options:
            return (rule, f"must be one of {', '.join(options)}")
        return None
    return check


def _version(value):
    if type(value) is not int or value != SCHEMA_VERSION:  # noqa: E721 - bool is not a version
        return ("SCHEMA", f"version must be {SCHEMA_VERSION}")
    return None


def _non_empty_list(value):
    return None if isinstance(value, list) and value else ("SCHEMA", "must be a non-empty list")


_slug = _bounded(_SLUG, 32, "a short lowercase slug like claude-mini")


def _pins(value):
    if not isinstance(value, list) or not value:
        return ("SCHEMA", "'machines' must list at least one machine id string")
    for pin in value:
        if not isinstance(pin, str):
            return ("SCHEMA", "'machines' must list at least one machine id string")
        if _slug(pin) is not None:
            return ("BAD_VALUE", "each pinned machine must be a machine id slug")
    return None


GRAMMAR = {
    ("map", "version"): _version,
    ("map", "machines"): _non_empty_list,
    ("map", "accounts"): _non_empty_list,
    ("machine", "id"): _slug,
    ("machine", "host"): _nullable(_bounded(_HOST, 63, "a short hostname like Phills-Mac-mini",
                                            max_seg=MAX_RUN)),
    ("machine", "notes"): _nullable(_text(_prose)),
    ("account", "label"): _slug,
    ("account", "provider"): _choice(PROVIDERS, "BAD_PROVIDER"),
    ("account", "plan"): _nullable(_choice(PLANS)),
    ("account", "email"): _email,
    ("account", "machines"): _pins,
    ("account", "notes"): _nullable(_text(_prose)),
}


def check_comment(text: str):
    """A YAML comment: one line of plain words, like notes, but file names are allowed.
    Punctuation such as @ + = & * and letter/digit mixes are refused."""
    body = text.lstrip("#").strip()
    ok = len(body) <= MAX_PROSE and _COMMENT_CHARS.fullmatch(body) is not None
    for word in body.split(" ") if ok else ():
        word = word.strip("(\"'.").rstrip(",.;:)'\"?!")
        if word and not (_COMMENT_WORD.fullmatch(word) and _runs_ok(word)):
            ok = False
    if not ok:
        return ("BAD_VALUE", "comments must be plain words (letters, a number of up to 4 digits, a ticket id "
                "or a file name), at most 160 characters, no codes, keys or symbols "
                "such as @ + = & *")
    return None
