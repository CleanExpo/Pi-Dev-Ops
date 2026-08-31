"""swarm/path_allowlist.py — is this path inside an allowlisted prefix?

Extracted from `tmux_validator.py`, which sits at its 464-line size-gate
baseline and may not grow. It is also the right home on its own terms: this is a
pure function of (path, prefixes) with no policy loading, no YAML and no I/O, so
it can be reasoned about and tested without the validator around it.

It answers one question for a security control, and has been wrong twice:

  1. A prefix expanding to "/" matched every absolute path. `~` is in the cd
     allowlist and `Path("~").expanduser()` is "/" whenever HOME=/, so
     `"/".rstrip("/") + "/"` was "/" — which every absolute path starts with.
     The sandbox silently stopped constraining anything.
  2. Comparing raw text let `/tmp/../var/log` pass as "under /tmp" and then run
     in /var/log. Every entry could be escaped by walking up out of it.

Both now fail CLOSED, and both are pinned by
`tests/swarm/test_tmux_validator_home.py`. The lesson the two share is that a
prefix check is only as good as what it compares: expand and normalise first, or
the string being tested is not the path that will be entered.
"""
from __future__ import annotations

import os
from pathlib import Path


def canonical(path: str) -> str:
    """`~` expanded and `.` / `..` collapsed.

    Lexical (`normpath`), deliberately NOT `Path.resolve()`: resolve touches the
    filesystem and follows symlinks, so the verdict would depend on what happens
    to exist on the box and on links an attacker may control. Purely textual is
    both stricter and reproducible.
    """
    expanded = str(Path(path).expanduser()) if path.startswith("~") else path
    return os.path.normpath(expanded)


def under_any_prefix(target: str, prefixes: list[str]) -> bool:
    """True when `target` is one of `prefixes` or lives beneath one.

    Both sides are canonicalised before comparison. A prefix that canonicalises
    to "/" is SKIPPED rather than honoured — it cannot constrain anything, and
    treating it as an allowlist entry is what voided the sandbox under HOME=/.

    The separator in `exp.rstrip("/") + "/"` is what stops `/tmpevil` passing
    because it happens to start with the characters of `/tmp`.
    """
    target = canonical(target)
    for prefix in prefixes:
        if not prefix:
            continue
        exp = canonical(prefix)
        if exp == "/":
            continue
        if target == exp or target.startswith(exp.rstrip("/") + "/"):
            return True
    return False


__all__ = ["canonical", "under_any_prefix"]
