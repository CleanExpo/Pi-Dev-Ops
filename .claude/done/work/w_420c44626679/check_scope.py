#!/usr/bin/env python3
"""C1 + C3: settings.json parses, its deny list gains exactly the merge rule, nothing else changes."""
import json, subprocess, sys

RULE = 'Bash(gh pr ' + 'merge:*)'
cur = json.load(open('.claude/settings.json'))
base = json.loads(subprocess.run(['git', 'show', 'origin/main:.claude/settings.json'],
                                 capture_output=True, text=True, check=True).stdout)
mode = sys.argv[1] if len(sys.argv) > 1 else 'c3'
deny = cur.get('permissions', {}).get('deny', [])
if mode == 'c1':
    ok = RULE in deny
    print(('PASS' if ok else 'FAIL') + ': deny list %s the merge rule' % ('has' if ok else 'lacks'))
    sys.exit(0 if ok else 1)
base_deny = base.get('permissions', {}).get('deny', [])
added = [r for r in deny if r not in base_deny]
removed = [r for r in base_deny if r not in deny]
cur_rest = dict(cur); cur_rest['permissions'] = {k: v for k, v in cur['permissions'].items() if k != 'deny'}
base_rest = dict(base); base_rest['permissions'] = {k: v for k, v in base['permissions'].items() if k != 'deny'}
ok = added == [RULE] and not removed and cur_rest == base_rest
print(('PASS' if ok else 'FAIL') + ': added=%s removed=%s other_keys_equal=%s' % (added, removed, cur_rest == base_rest))
sys.exit(0 if ok else 1)
