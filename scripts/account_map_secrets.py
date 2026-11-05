"""Credential-shape patterns for the account map validator (RA-8187).

Kept apart from check_account_map.py so the schema rules and the "does this look like a
secret" rules (the second net) can each be read on one screen. It also holds the YAML
loader that refuses duplicate keys. All are read-only; nothing here stores, prints or
transmits a matched value.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

# A key whose NAME suggests a credential, at any depth of the map.
SECRET_NAME = re.compile(
    r"token|secret|passw|api[_-]?key|apikey|cookie|session|credential|bearer|"
    r"private[_-]?key|auth|otp|refresh",
    re.I,
)

# Second net (the first is the accept-only grammar in account_map_grammar.py). It runs on
# every parsed key and string value and on every raw line, comments included. No leading
# \b: "_" is a word character, so "x_lin_api_..." would slip past a word boundary. The
# lookbehind only stops a match starting inside an ordinary word (e.g. "task-").
_START = r"(?<![A-Za-z0-9])"
OWN_PATTERNS = [
    re.compile(_START + r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(_START + r"lin_(?:api|oauth)_[A-Za-z0-9]{20,}"),
    re.compile(_START + r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(_START + r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(_START + r"xox[abeoprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"Bearer\s+\S+", re.I),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"-----BEGIN [A-Z ]*KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # A long unbroken run of letters and digits (both present) reads as a raw token.
    re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{32,}"),
    # A credential word followed by ':' or '=' and a value: "password=...", "api key: ...".
    re.compile(r"(?:password|passwd|pwd|token|secret|api[_ -]?key|apikey|cookie|"
               r"session[_ -]?(?:id|key|token|cookie)?|credential|auth|bearer|otp)s?"
               r"\s*[:=]\s*\S", re.I),
]

# The repo scanner's own list, read from its source (not imported: importing it pulls in
# server config). Reused rather than copied so the two lists cannot drift apart.
SCANNER_PATH = Path(__file__).resolve().parent.parent / "app" / "server" / "scanner.py"
_scanner_cache: dict = {}


class ScannerPatternsError(RuntimeError):
    """The scanner's _SECRET_PATTERNS could not be read; the check must not pass."""


def scanner_patterns() -> list:
    path = SCANNER_PATH
    if path not in _scanner_cache:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            node = next(n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                        and "_SECRET_PATTERNS" in [getattr(t, "id", None) for t in
                                                   (n.targets if isinstance(n, ast.Assign)
                                                    else [n.target])])
            entries = ast.literal_eval(node.value)
            _scanner_cache[path] = [re.compile(entry[0]) for entry in entries]
        except (OSError, SyntaxError, StopIteration, ValueError, TypeError, re.error) as exc:
            raise ScannerPatternsError(f"cannot read _SECRET_PATTERNS from {path}: "
                                       f"{type(exc).__name__}") from exc
        if not _scanner_cache[path]:
            raise ScannerPatternsError(f"_SECRET_PATTERNS in {path} is empty")
    return _scanner_cache[path]


class DuplicateKeyError(yaml.YAMLError):
    """Two equal keys in one mapping. PyYAML would keep the last and hide the first."""


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys, so no value can sit unparsed in the file."""


def _construct_unique_mapping(loader, node):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in seen
            seen.add(key)
        except TypeError:  # unhashable key: construct_mapping raises its own error
            continue
        if duplicate:
            raise DuplicateKeyError(f"line {key_node.start_mark.line + 1}: a key "
                                    "appears twice in one mapping")
    return loader.construct_mapping(node, deep=True)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                _construct_unique_mapping)


def looks_secret_name(name) -> bool:
    return bool(SECRET_NAME.search(str(name)))


def looks_secret_value(text: str) -> bool:
    return any(p.search(text) for p in OWN_PATTERNS + scanner_patterns())


def comment_lines(text: str):
    """Yield (line number, comment text) for every YAML comment; the parser drops these."""
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            yield number, stripped
        elif " #" in line:
            yield number, line.split(" #", 1)[1]
