"""Mutants for round 22 onward; the earlier lists are at the 300-line limit. Chained after GUARD_MUTANTS."""
from jev_platform_guard_mutants import GUARD_MUTANTS as _GUARD

GUARD_MUTANTS = _GUARD + [
    # round 22: one credential set, screened decoded in client.send and the eval harness; no error body is read
    # (test_jev_platform_harness_screen.py, test_jev_platform_send_screen.py)
    ('client.py', 'return any(p.search(text) for p in CREDENTIALS)', 'return False'),
    ('client.py', ')] + [_API_KEYS]', ')]'),
    ('client.py', '        return credential(obj)', '        return False'),
    ('client.py', 'credential_payload(k) or credential_payload(v)', 'credential_payload(v)'),
    ('client.py', '    if isinstance(obj, (list, tuple)):\n        return any(credential_payload',
     '    if False:\n        return any(credential_payload'),
    ('client.py', '    if credential_payload(body):  # round 22', '    if False:  # round 22'),
    ('evals/jev_constitution/harness.py',
     '    if any(client.credential(str(c.get("state", ""))) for c in cases):', '    if False:'),
    ('evals/jev_constitution/harness.py', '    if client.credential_payload(body):\n        return 0, None, 0.0',
     '    if False:\n        return 0, None, 0.0'),
    ('evals/jev_constitution/harness.py', '"HTTP error body not read"', 'e.read()[:300].decode(errors="replace")'),
]
