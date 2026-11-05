"""Credential-shape patterns for the account map validator (RA-8187).

Kept apart from check_account_map.py so the schema rules and the "does this look like a
secret" rules can each be read on one screen. Both are read-only checks; nothing here
stores, prints or transmits a matched value.
"""
from __future__ import annotations

import re

# A key whose NAME suggests a credential, at any depth of the map.
SECRET_NAME = re.compile(
    r"token|secret|passw|api[_-]?key|apikey|cookie|session|credential|bearer|"
    r"private[_-]?key|auth|otp|refresh",
    re.I,
)

# A string VALUE (or comment) whose content looks like a pasted credential.
SECRET_VALUE = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bBearer\s+\S+", re.I),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"-----BEGIN [A-Z ]*KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # A long unbroken run of letters and digits (both present) reads as a raw token.
    # Hyphens break the run, so URL slugs and labels are not flagged.
    re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{32,}\b"),
    # A credential word followed by ':' or '=' and a value: "password=...", "api key: ...".
    # Talking about a password ("rotate the password monthly") is not flagged.
    re.compile(r"\b(?:password|passwd|pwd|token|secret|api[_ -]?key|apikey|cookie|"
               r"session[_ -]?(?:id|key|token|cookie)?|credential|auth|bearer|otp)s?"
               r"\s*[:=]\s*\S", re.I),
]


def looks_secret_name(name) -> bool:
    return bool(SECRET_NAME.search(str(name)))


def looks_secret_value(text: str) -> bool:
    return any(p.search(text) for p in SECRET_VALUE)


def comment_lines(text: str):
    """Yield (line number, comment text) for every YAML comment; the parser drops these."""
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            yield number, stripped
        elif " #" in line:
            yield number, line.split(" #", 1)[1]
