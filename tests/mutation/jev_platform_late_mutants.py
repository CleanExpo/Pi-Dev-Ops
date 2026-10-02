"""Mutants for round 22 onward; the earlier lists are at the 300-line limit. Chained after GUARD_MUTANTS."""
from jev_platform_guard_mutants import GUARD_MUTANTS as _GUARD

GUARD_MUTANTS = _GUARD + [
    # round 22: one credential set, screened decoded in client.send and the eval harness; no error body is read
    # (test_jev_platform_harness_screen.py, test_jev_platform_send_screen.py)
    ('client.py', 'return any(p.search(t) for t in screened(text) for p in CREDENTIALS)', 'return False'),
    ('client.py', ')] \\\n    + [_API_KEYS]', ')]'),
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
    # round 23: edges are ASCII letter/digit lookarounds, never \\b (test_jev_platform_edge_screen.py)
    ('client.py', '_EDGE, _END = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"', '_EDGE, _END = r"\\b", r"\\b"'),
    ('client.py', 'r"AKIA[0-9A-Z]{16}" + _END', 'r"AKIA[0-9A-Z]{16}\\b"'),
    ('client.py', 're.compile(_EDGE + r"[0-9a-fA-F]{32,}" + _END)', 're.compile(r"\\b[0-9a-fA-F]{32,}\\b")'),
    ('ask.py', 'client._EDGE + r"iicrc" + client._END', 'r"\\biicrc\\b"'),
    # round 24: re.ASCII, or re.I folds U+212A/U+0130/U+0131/U+017F into the ASCII edge classes
    ('client.py', 're.compile(p, re.I | re.ASCII) for p in (  # ASCII', 're.compile(p, re.I) for p in (  # ASCII'),
    ('ask.py', '[re.compile(p, re.I | re.ASCII) for p in (client._EDGE', '[re.compile(p, re.I) for p in (client._EDGE'),
    # round 25: one private snapshot is screened and sent on every retry (test_jev_platform_retry_snapshot.py)
    ('client.py', '    body = json.loads(json.dumps(body))  # round 25', '    body = body  # round 25'),
    ('scout.py', '    body = json.loads(json.dumps(body))  # round 25', '    body = body  # round 25'),
    # round 26: provider replies refuse duplicate keys (test_jev_platform_duplicate_reply.py)
    ('client.py', '        if k in out:\n            raise json.JSONDecodeError(', '        if False:\n            raise json.JSONDecodeError('),
    ('__main__.py', 'client.strict_json(resp.read().decode()), None', 'json.loads(resp.read().decode()), None'),
    ('gemini.py', 'return resp.status, client.strict_json(resp.read().decode())', 'return resp.status, json.loads(resp.read().decode())'),
    ('evals/jev_constitution/harness.py', 'client.strict_json(resp.read().decode())', 'json.load(resp)'),
    # round 27: model-written JSON refuses duplicates too (test_jev_platform_duplicate_model_json.py)
    ('evals/jev_constitution/generate.py', 'return client.strict_json(m.group(1))', 'return json.loads(m.group(1))'),
    # round 29: screens read the raw text AND its escape-free reading (test_jev_platform_edge_screen.py LOG_ESCAPES)
    ('client.py', '    return text, _ANSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\\\\\", text)))', '    return (text,)'),
    ('client.py', '    return text, _ANSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\\\\\", text)))',
     '    return (_ANSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\\\\\", text))),)'),
    # round 30: nested escaping collapses, colour codes are removed
    ('client.py', '_ANSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\\\\\", text)))', '_ANSI.sub(" ", _ESCAPE.sub(" ", text))'),
    ('client.py', '_ANSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\\\\\", text)))', '_ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\\\\\", text))'),
    ('client.py', 'for t in screened(text) for p in CREDENTIALS', 'for t in (text,) for p in CREDENTIALS'),
    ('ask.py', 'for t in client.screened(text) for p in _REFUSE', 'for t in (text,) for p in _REFUSE'),
]
