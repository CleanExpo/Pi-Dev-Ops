"""Mutants for round 22 onward; the earlier lists are at the 300-line limit. Chained after GUARD_MUTANTS."""
from jev_platform_guard_mutants import GUARD_MUTANTS as _GUARD

GUARD_MUTANTS = _GUARD + [
    # round 22: the eval harness screens key material and never reads an error body
    # (test_jev_platform_harness_screen.py)
    ('ask.py', 'return any(p.search(text) for p in _CREDENTIALS)', 'return False'),
    ('ask.py', 'return any(p.search(text) for p in _CREDENTIALS)', 'return any(p.search(text) for p in _REFUSE)'),
    ('evals/jev_constitution/harness.py',
     '    if any(ask.credential(str(c.get("state", ""))) for c in cases):', '    if False:'),
    ('evals/jev_constitution/harness.py', 'for s in (state, *body', 'for s in (*body'),
    ('evals/jev_constitution/harness.py', '*body["questions"]["q"]["criteria"].values(),', ''),
    ('evals/jev_constitution/harness.py', '                                           question["question"])):',
     '                                           )):'),
    ('evals/jev_constitution/harness.py', '"HTTP error body not read"', 'e.read()[:300].decode(errors="replace")'),
]
