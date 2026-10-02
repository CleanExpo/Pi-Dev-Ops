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
    ('client.py', 'for t in screened(text) for p in CREDENTIALS', 'for t in (text,) for p in CREDENTIALS'),
    ('ask.py', 'for t in client.screened(text, decode) for p in _REFUSE', 'for t in (text,) for p in _REFUSE'),
    # rounds 30-31: four readings (raw, escape-blanked, decoded with colour codes as a gap / as nothing), bounded decode
    # round 33: the raw text and EVERY decoding stage are screened (gap + join), plus blanked; bounded
    ('client.py', '    return (blanked,) + tuple(r for t in stages for r in (_CSI.sub(" ", t), _CSI.sub("", t)))', '    return tuple(r for t in stages for r in (_CSI.sub(" ", t), _CSI.sub("", t)))'),
    ('client.py', '    return (blanked,) + tuple(r for t in stages for r in (_CSI.sub(" ", t), _CSI.sub("", t)))', '    return (blanked,) + tuple(r for t in stages for r in (_CSI.sub("", t),))'),
    ('client.py', '    return (blanked,) + tuple(r for t in stages for r in (_CSI.sub(" ", t), _CSI.sub("", t)))', '    return (blanked,) + tuple(r for t in stages for r in (_CSI.sub(" ", t),))'),
    ('client.py', '        frontier = nxt\n    return None', '        frontier = nxt\n    return stages'),
    ('client.py', '    stages, frontier = [text], [text]\n', '    stages, frontier = [], [text]\n'),
    ('client.py', '            return stages\n', '            return stages[-1:]\n'),
    ('client.py', '            return stages\n', '            return stages[:1] + stages[-1:]\n'),
    ('client.py', '        return text, blanked, "sk-unsettled-escape-depth"', '        return text, blanked'),
    ('client.py', '_CSI = re.compile(r"(?:\\x1b\\[|\\x9b)', '_CSI = re.compile(r"(?:\\x1b\\[)'),
    ('client.py', '_CSI = re.compile(r"(?:\\x1b\\[|\\x9b)[0-9:;<=>?]*', '_CSI = re.compile(r"(?:\\x1b\\[|\\x9b)[0-9;?]*'),
    ('client.py', '        return chr(n) if n <= 0x10FFFF else', '        return " " if n <= 0x10FFFF else'),
    ('client.py', 'for d in (_ESCAPE.sub(_decode_one, t), _python_decode(t)):', 'for d in (_ESCAPE.sub(" ", t), _python_decode(t)):'),
    ('client.py', '    blanked = _BLANKED_CSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub(',
     '    blanked = _BLANKED_CSI.sub(" ", _ESCAPE.sub(" ", (lambda x: x)('),
    # round 32: named escapes decode to their letter; backslash-newline (LF or CRLF) is a continuation
    ('client.py', '            return unicodedata.lookup(e[2:-1])', '            return " "'),
    ('client.py', '_SINGLE.update({"\\n": "", "\\r\\n": "", "\\r": ""})', '_SINGLE.update({"\\r\\n": "", "\\r": ""})'),
    ('client.py', '_SINGLE.update({"\\n": "", "\\r\\n": "", "\\r": ""})', '_SINGLE.update({"\\n": "", "\\r": ""})'),
    ('client.py', '_SINGLE.update({"\\n": "", "\\r\\n": "", "\\r": ""})', '_SINGLE.update({"\\n": "", "\\r\\n": ""})'),  # round 34: lone CR
    ('client.py', '[0-7]{1,3}|\\r\\n|.)', '[0-7]{1,3}|.)'),
    # round 36: Python's own unicode_escape reading is a second decoder, followed to the same fixpoint
    ('client.py', 'for d in (_ESCAPE.sub(_decode_one, t), _python_decode(t)):', 'for d in (_ESCAPE.sub(_decode_one, t),):'),
    ('client.py', 'for d in (_ESCAPE.sub(_decode_one, t), _python_decode(t)):', 'for d in (_python_decode(t),):'),
    ('client.py', '            return text.encode("latin-1", "backslashreplace").decode("unicode_escape")', '            return text'),
    ('client.py', '        except UnicodeDecodeError:\n            return text\n', '        except UnicodeDecodeError:\n            raise\n'),
    ('client.py', '        warnings.simplefilter("ignore")', '        warnings.simplefilter("error")'),
    ('client.py', '        frontier = nxt\n', '        frontier = frontier\n'),
    ('client.py', '                if d not in stages:', '                if True:'),
]
