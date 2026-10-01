"""Guard-sweep mutants (29/09): every guard that no test could fail, with the test that now kills it.

Imported by jev_platform_mutants.py, which runs them after its own list."""
GUARD_MUTANTS = [
    # guard sweep 29/09: scout/client/agent/gemini
    ('scout.py', 'if not isinstance(answers, dict) or set(answers) != {tid} or not isinstance(answers[tid], dict):',
     'if not isinstance(answers, dict) or tid not in answers or not isinstance(answers[tid], dict):'),
    ('scout.py', 'if a.get("type") != "choice" or not policy.valid_noul(a.get("confidence"))',
     'if not policy.valid_noul(a.get("confidence"))'),
    ('scout.py', 'if a.get("type") != "choice" or not policy.valid_noul(a.get("confidence")) '
                 'or not isinstance(probs, dict)',
     'if a.get("type") != "choice" or not isinstance(a.get("confidence"), (int, float)) '
     'or not isinstance(probs, dict)'),
    ('scout.py', '            or not all(policy.valid_noul(v) for v in probs.values()):\n'
                 '        return None\n    if a.get',
     '            or False:\n        return None\n    if a.get'),
    ('scout.py', 'if a.get("choice") not in allowed or not set(probs) <= allowed:',
     'if a.get("choice") not in allowed:'),
    ('scout.py', 'if a.get("choice") not in allowed or not set(probs) <= allowed:', 'if not set(probs) <= allowed:'),
    ('scout.py', 'if rel in manifest["files"] and not (ask._DENY_NAMES.search(rel) or ask.sensitive(rel)):',
     'if rel in manifest["files"]:'),
    ('scout.py', 'if not paths or len(paths) > MAX_BUNDLE or len(set(paths)) != len(paths):',
     'if not paths or len(paths) > MAX_BUNDLE:'),
    ('scout.py', 'if not paths or len(paths) > MAX_BUNDLE or len(set(paths)) != len(paths):',
     'if len(paths) > MAX_BUNDLE or len(set(paths)) != len(paths):'),
    ('scout.py', '    if answers is None:\n        return {"outcome": "unavailable"',
     '    if False:\n        return {"outcome": "unavailable"'),
    ('client.py', 'and 0 <= tokens <= RESERVE_TOKENS:', ':'),
    ('client.py', 'if isinstance(tokens, int) and not isinstance(tokens, bool) and', 'if isinstance(tokens, int) and'),
    ('client.py', 'if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):',
     'if not isinstance(data, dict):'),
    ('client.py', 'if not isinstance(a, dict) or a.get("type") != "noul" or not policy.valid_noul(a.get("noul")):',
     'if not isinstance(a, dict) or not policy.valid_noul(a.get("noul")):'),
    ('client.py', 'if status != 429 or attempt == MAX_RETRIES', 'if attempt == MAX_RETRIES'),
    ('client.py', 'or wait is None or', 'or'),
    ('agent_tools.py', '    if not isinstance(args, dict):\n        return "arguments must be an object"',
     '    if False:\n        return "arguments must be an object"'),
    ('agent_tools.py', '        if not ok:\n            return f"argument',
     '        if False:\n            return f"argument'),
    ('agent_tools.py', 'isinstance(v, list) and all(isinstance(x, str) for x in v)', 'isinstance(v, list)'),
    ('agent_tools.py', 'if v is None and name == "propose_template":', 'if v is None:'),
    ('agent_tools.py', '    if "blocked" in out:\n        return {"refused": out["blocked"]}',
     '    if False:\n        return {"refused": out["blocked"]}'),
    ('agent.py', 'if finish == "MALFORMED_FUNCTION_CALL" or not all(', 'if not all('),
    ('agent.py', 'if isinstance(p.get("text"), str) and not p.get("thought"))', 'if isinstance(p.get("text"), str))'),
    ('agent.py', 'gemini.GeminiBudget(min(a.max_usd, gemini.RUN_CAP_USD), price)',
     'gemini.GeminiBudget(a.max_usd, price)'),
    ('agent.py', 'return 0 if ledger["outcome"] == "complete" else 1', 'return 0'),
    ('agent.py', 'repo = cli_scale.repo_root(a.repo) if cli_scale._jev_ready() else None',
     'repo = cli_scale.repo_root(a.repo)'),
    ('gemini.py', '            if self.attempts >= self.max_attempts or self.spent + cost > self.max_usd + 1e-12:\n'
                  '                return None',
     '            if self.spent + cost > self.max_usd + 1e-12:\n                return None'),
    ('gemini.py', 'if prompt is None or not isinstance(t, int) or isinstance(t, bool) or t < 0:',
     'if not isinstance(t, int) or isinstance(t, bool) or t < 0:'),
    # guard sweep 29/09: engine/cli/calibration/policy
    ('engine.py', 'if rules and not problems else',
     'if rules else'),  # en-notsent
    ('engine.py', 'return None if not path.exists() else {"corrupt": True}',
     'return None'),  # en-loadrecord-corrupt
    ('engine.py', '    if record is None:\n        return "FAIL", ["absent"]',
     '    if False:\n        return "FAIL", ["absent"]'),  # en-rating-absent
    ('engine.py', 'b is not None and (verified.read(ROOT, r.as_posix(), commit) or ("", None))[1] == b',
     'b is not None and (verified.read(ROOT, r.as_posix(), commit) or ("", None))[1] is not None'),  # en-rating-tracked
    ('engine.py', 'and commit is not None and all(', 'and commit is not None and any('),  # en-rating-each
    ('policy.py', '"coverage": "FAIL" if evaluated < RULE_COUNT else "A",',
     '"coverage": "A",'),  # po-coverage
    ('calibration.py', ' or not isinstance(record["label_provenance"], dict):\n        return "corrupt"',
     ':\n        return "corrupt"'),  # ca-es-prov
    ('calibration.py', '    if record["state"] != policy.USABLE_STATE:\n        return record["state"]',
     '    if False:\n        return record["state"]'),  # ca-es-state
    ('calibration.py', '    if any(k not in record for k in REQUIRED):\n        return ["missing required fields"]',
     '    if False:\n        return ["missing required fields"]'),  # ca-verify-required
    ('calibration.py', 'for key in ("threshold", "state", "split", "counters", "miss_rate_upper_95"):',
     'for key in ("state", "split", "counters", "miss_rate_upper_95"):'),  # ca-verify-keys-thr
    ('calibration.py', 'for key in ("threshold", "state", "split", "counters", "miss_rate_upper_95"):',
     'for key in ("threshold", "state", "split", "counters"):'),  # ca-verify-keys-bound
    ('calibration.py', ' or violations < MIN_PER_SIDE or compliant < MIN_PER_SIDE:',
     ' or violations < MIN_PER_SIDE:'),  # ca-state-mincomp
    ('calibration.py', '    if threshold is None:\n        return "no_qualifying_threshold"',
     '    if False:\n        return "no_qualifying_threshold"'),  # ca-state-none
    ('__main__.py', 'def cmd_calibrate(a) -> int:\n    if not _live_ready():',
     'def cmd_calibrate(a) -> int:\n    if False:'),  # mn-calib-ready
    ('__main__.py', 'return 0 if rec.get("state") not in ("incomplete", None) else 1',
     'return 0'),  # mn-calib-rc
    ('__main__.py', 'return 0 if rating in ("AA", "AAA") else 1',
     'return 0'),  # mn-verify-rc
    ('__main__.py', 'def cmd_ask(a) -> int:\n    if not _live_ready():',
     'def cmd_ask(a) -> int:\n    if False:'),  # mn-ask-ready
    ('__main__.py', '    return 2 if "blocked" in out else 0\n\n\ndef cmd_approve',
     '    return 0\n\n\ndef cmd_approve'),  # mn-ask-rc
    ('__main__.py', '    if sum(x is not None for x in (a.path, a.glob, a.prompt_file)) != 1 or (a.prompt_file is None) != (a.id is None):',
     '    if False:'),  # mn-approve-one
    ('__main__.py', ' != 1 or (a.prompt_file is None) != (a.id is None):',
     ' != 1:'),  # mn-approve-id
    ('__main__.py', 'return 2 if a.path is None and "files" not in out and "prompts" not in out else 0',
     'return 0'),  # mn-approve-rc
    ('__main__.py', '    if a.cmd == "ask" and len(a.file) > 50:',
     '    if False:'),  # mn-50files
    ('cli_scale.py', '    if path is not None and not os.path.isabs(path):',
     '    if False:'),  # cs-isabs
    ('cli_scale.py', '    return top or None',
     "    return top or (path or '.')"),  # cs-toplevel
    ('cli_scale.py', '    if not _jev_ready():\n        return 2',
     '    if False:\n        return 2'),  # cs-ready
    ('cli_scale.py', '    if not os.environ.get("TYPESAFE_API_KEY", "").strip():',
     '    if False:'),  # cs-jevready
    ('cli_scale.py', '    if repo is None:\n        return 2',
     '    if False:\n        return 2'),  # cs-repo-none
    ('cli_scale.py', 'return 2 if "blocked" in out or out.get("outcome") == "refused" else 0',
     'return 0'),  # cs-rc
    ('cli_scale.py', 'return 2 if "blocked" in out or out.get("outcome") == "refused" else 0',
     'return 2 if "blocked" in out else 0'),  # cs-rc-refused
    ('cli_scale.py', 'return 2 if "blocked" in out or out.get("outcome") == "refused" else 0',
     'return 2 if out.get("outcome") == "refused" else 0'),  # cs-rc-blocked
    # guard sweep 29/09: evals
    ('evals/jev_constitution/quotes.py',
     '        if found[2] != b"120000":',
     '        if True:'),
    ('evals/jev_constitution/quotes.py',
     '    return 1 if drift else 0',
     '    return 0'),
    ('evals/jev_constitution/harness.py',
     '    if status != 200 or not isinstance(resp, dict):',
     '    if not isinstance(resp, dict):'),
    ('evals/jev_constitution/harness.py',
     'return EXIT_OK if verdicts and ok == len(verdicts) else EXIT_INVALID',
     'return EXIT_OK'),
    ('evals/jev_constitution/generate.py',
     'return {k: v for k, v in os.environ.items() if k not in _SCRUB}',
     'return dict(os.environ)'),
    ('evals/jev_constitution/generate.py',
     '    if not isinstance(items, list):\n        raise ValueError("writer reply',
     '    if False:\n        raise ValueError("writer reply'),
    ('evals/jev_constitution/generate.py',
     'if not isinstance(parts, list) or first.get("finishReason") not in (None, "STOP"):',
     'if not isinstance(parts, list):'),
    ('evals/jev_constitution/generate.py',
     'and isinstance(p.get("text"), str)\n                   and not p.get("thought"))',
     'and isinstance(p.get("text"), str))'),
    ('evals/jev_constitution/generate.py',
     '    if len(labels) != len(states):',
     '    if False:'),
    ('evals/jev_constitution/generate.py',
     'return [x if isinstance(x, bool) else None for x in labels]',
     'return list(labels)'),
    ('evals/jev_constitution/generate.py',
     '    if not key or price is None:\n',
     '    if False:\n'),
    ('evals/jev_constitution/generate.py',
     'return write, "gemini", CASES / f"{args.question}.gemini.jsonl"',
     'return write, "gemini", CASES / f"{args.question}.jsonl"'),
    ('evals/jev_constitution/writer_control.py',
     'return None if isinstance(claim, bool) or not isinstance(claim, int) else',
     'return None if False else'),
    ('evals/jev_constitution/writer_control.py',
     'return None if isinstance(claim, bool) or not isinstance(claim, int) else',
     'return None if not isinstance(claim, int) else'),
    ('evals/jev_constitution/writer_control.py',
     '    if not isinstance(case, dict) or not isinstance(case.get("label"), bool) '
     'or not isinstance(case.get("state"), str) \\\n            or not case["state"].strip():\n        return False',
     '    if not isinstance(case, dict):\n        return False'),
    ('evals/jev_constitution/writer_control.py',
     ' \\\n            or not case["state"].strip():\n        return False',
     ':\n        return False'),
    ('evals/jev_constitution/writer_control.py',
     'return cls not in ANCHOR_FIELDS or anchor_truth({**case, "class": cls}) is not None',
     'return True'),
    ('evals/jev_constitution/writer_control.py',
     '    items = items[:requested]',
     '    items = items'),
    ('evals/jev_constitution/writer_control.py',
     'budget = gemini.GeminiBudget(gemini.WRITER_CAP_USD, price)',
     'budget = gemini.GeminiBudget(100.0, price)'),
    # guard sweep 29/09: ask/manifest
    ("ask.py", "    if not isinstance(data, dict):  # a list", "    if False:  # a list"),  # the bug fix
    ('ask.py', 'p in ("", ".", "..") for p in parts', 'p in ("", ".") for p in parts'),
    ("ask.py", "return os.read(leaf, MAX_FILE_BYTES + 1)", "return os.read(leaf, MAX_FILE_BYTES)"),
    ("ask.py", "    if len(raw) > MAX_FILE_BYTES:\n        return None, digest", "    if False:\n        return None, digest"),
    ('ask.py', 'return data if isinstance(data.get("files"), dict) and isinstance(data.get("questions"), dict) else None', 'return data if isinstance(data, dict) else None'),
    ('ask.py', 'isinstance(data.get("files"), dict) and isinstance(data.get("questions"), dict)', 'isinstance(data.get("files"), dict)'),
    ('ask.py', 'all(isinstance(t.get(k), str) for k in ("question", "true", "false"))', 'True'),
    ('ask.py', 'and 2 <= len(t["options"]) <= 255 and', 'and'),
    ('ask.py', 'all(isinstance(v, str) for v in t["options"].values())', 'True'),
    ("ask.py", "if not template_ids or len(template_ids) > MAX_QUESTIONS:", "if not template_ids:"),
    ("ask.py", "if len(text) > MAX_TEMPLATE_CHARS or sensitive(text) or", "if sensitive(text) or"),
    ("ask.py", "if len(text) > MAX_TEMPLATE_CHARS or sensitive(text) or", "if len(text) > MAX_TEMPLATE_CHARS or"),
    ('ask.py', 'if not isinstance(a, dict) or a.get("type") != q["type"]:', 'if not isinstance(a, dict):'),
    ('ask.py', 'if policy.valid_noul(a.get("noul")) else None', 'if a.get("noul") is not None else None'),
    ("ask.py", "            or not set(probs) <= allowed or not all(", "            or not all("),
    ('ask.py', 'or not all(policy.valid_noul(v) for v in probs.values()):\n        return None\n    return {"type": "choice"', 'or False:\n        return None\n    return {"type": "choice"'),
    ("manifest.py", "isinstance(v, str) and v.strip() for v in opts.values()", "isinstance(v, str) for v in opts.values()"),
    ('manifest.py', '        if template_state(t) != ("task", "files"):', '        if False:'),
    ('manifest.py', '    return f"template {tid}: unknown type"', '    return None'),
    ('manifest.py', 'if not isinstance(t, dict) or not isinstance(t.get("question"), str) or not t["question"].strip():', 'if not isinstance(t, dict):'),
    ("manifest.py", "if not isinstance(state, list) or tuple(state) not in STATES:", "if tuple(state) not in STATES:"),
    ('manifest.py', '    if len(t["question"]) > ask.MAX_TEMPLATE_CHARS:', '    if False:'),
    ("manifest.py", "    if not isinstance(prompts, dict) or not all(\n            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in prompts.items()):", "    if False:"),
    ("manifest.py", "isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in prompts.items()", "isinstance(k, str) and isinstance(v, str) for k, v in prompts.items()"),
    ("manifest.py", "if rel == ask.MANIFEST or ask._DENY_NAMES.search(rel) or ask.sensitive(rel):", "if rel == ask.MANIFEST or ask._DENY_NAMES.search(rel):"),
    ("manifest.py", "        except (OSError, ValueError) as e:\n            refused[rel]", "        except (KeyError) as e:\n            refused[rel]"),
    ("manifest.py", "        if len(raw) > ask.MAX_FILE_BYTES:\n            refused[rel]", "        if False:\n            refused[rel]"),
    ("manifest.py", "    if not text.strip() or ask.sensitive(text):", "    if ask.sensitive(text):"),
    ("manifest.py", "    if not text.strip() or ask.sensitive(text):", "    if not text.strip():"),
    # round 10 P1s: committed inputs only (tests/test_jev_platform_committed_inputs.py)
    ('engine.py', '    found = _committed(QUESTIONS, rev)\n',
     '    found = ("", QUESTIONS.read_text()) if QUESTIONS.exists() else None\n'),  # en-registry-head
    ('engine.py', '    committed = _committed(CASES / f"{rule_id}.jsonl", commit) if rule else None\n',
     '    committed = ((_committed(CASES / f"{rule_id}.jsonl", commit) or ("", ""))[0], '
     '(CASES / f"{rule_id}.jsonl").read_text()) if rule else None\n'),  # en-cases-head
    ('engine.py', '"cases_blob": committed[0]}',
     '"cases_blob": _git("rev-parse", "HEAD")}'),  # en-cases-blob
    ('engine.py', 'None if cases and all(_dual_labelled(c) for c in cases) else',
     'None if cases else'),  # en-calib-dual
    ('engine.py', '        problems = calibration.verify(record, scored) or _lineage_problems(rule["id"], record, scored,\n'
     '                                                                           verified.resolve(ROOT))\n',
     '        problems = calibration.verify(record, scored)\n'),  # en-state-lineage
    ('engine.py', '    problems = calibration.verify(record, scored) or _lineage_problems(rule_id, record, scored, commit)\n'
     '    if problems:', '    problems = calibration.verify(record, scored)\n    if problems:'),  # en-rating-lineage
    # round 18: the lineage judges the commit the receipt names (test_jev_platform_binding_bytes.py)
    ('engine.py', '_lineage_problems(rule_id, record, scored, commit)',
     '_lineage_problems(rule_id, record, scored, verified.resolve(ROOT))'),  # en-rating-lineage-head
    ('engine.py', '    if not all(_dual_labelled(c) for c in cases):\n        return ["cases_blob',
     '    if False:\n        return ["cases_blob'),  # en-lineage-dual
    ('engine.py', 'return [] if want == have else', 'return [] if True else'),  # en-lineage-match
    # round 11 P1s: reviewed ids name reviewed bytes; lineage is a commit in HEAD's history
    # (tests/test_jev_platform_git_integrity.py)
    ('committed.py', '["git", "--no-replace-objects", "-C", str(repo), "cat-file", "--batch"]',
     '["git", "-C", str(repo), "cat-file", "--batch"]'),  # co-no-replace
    ('committed.py', 'return data if header[1] == kind and _hash_ok(oid, kind, data) else None',
     'return data'),  # co-rehash
    ('committed.py', 'return data if header[1] == kind and _hash_ok(oid, kind, data) else None',
     'return data if _hash_ok(oid, header[1], data) else None'),  # co-type
    ('committed.py', '        if not is_oid(oid):  # a name', '        if False:  # a name'),  # co-oid-only
    ('committed.py', '            if oid == ancestor:\n                return True',
     '            if True:\n                return True'),  # co-ancestor
    ('engine.py', '    if not verified.is_oid(sha):\n        return', '    if False:\n        return'),  # en-lineage-sha
    ('committed.py', '        if base.joinpath(*rel.parts[:depth]).is_symlink():\n            return None',
     '        if False:\n            return None'),  # co-no-symlink (round 13)
    ('evals/jev_constitution/generate.py', 'verified.file_at_head(REPO, WRITER_CONTROL,',
     'verified.file_at_head(WRITER_CONTROL.parent, WRITER_CONTROL,'),  # ge-root-given (round 14)
    ('engine.py', ' != blob:\n        return ["cases_blob is not the cases file',
     ' != blob and False:\n        return ["cases_blob is not the cases file'),  # en-lineage-at-sha
    ('engine.py', '    if not verified.is_ancestor(ROOT, sha, head or ""):\n',
     '    if False:\n'),  # en-lineage-ancestor
    ('evals/jev_constitution/harness.py', '    data = verified.file_at_head(REPO, path)',
     '    data = __import__("subprocess").run(["git", "-C", str(path.parent), "show", f"HEAD:./{path.name}"], '
     'capture_output=True).stdout or None'),  # ha-verified
    ('__main__.py', 'json.loads(verified.at_head(engine.ROOT, FIXTURE_AT_HEAD)[2])',
     'json.loads(engine._git("show", f"HEAD:{FIXTURE_AT_HEAD}"))'),  # cli-fixture-verified
    ('evals/jev_constitution/generate.py', 'shown = verified.file_at_head(REPO, WRITER_CONTROL, env={"PATH": os.environ.get("PATH", "")})',
     'shown = subprocess.run(["git", "-C", str(WRITER_CONTROL.parent), "show", f"HEAD:./{WRITER_CONTROL.name}"], '
     'capture_output=True).stdout or None'),  # ge-control-verified
    ('evals/jev_constitution/quotes.py', '        if found is None:\n            raise ValueError',
     '        if found is None:\n            return ""\n            raise ValueError'),  # qu-refuse
    ('evals/jev_constitution/harness.py', '    questions = committed_questions()',
     '    questions = load_questions()'),  # ha-questions-head
    ('evals/jev_constitution/harness.py', '        cases = committed_cases(q["id"])',
     '        cases = load_cases(q["id"])'),  # ha-cases-head
    ('evals/jev_constitution/harness.py', 'problems = question_problems(q, cases=cases)',
     'problems = question_problems(q)'),  # ha-validate-sent
    ('evals/jev_constitution/generate.py', 'for q in committed_questions() if q["id"] == args.question',
     'for q in __import__("evals.jev_constitution.harness", fromlist=["h"]).load_questions() '
     'if q["id"] == args.question'),  # ge-question-head
    ('evals/jev_constitution/writer_control.py', 'for q in committed_questions() if q["id"] == QUESTION_ID',
     'for q in __import__("evals.jev_constitution.harness", fromlist=["h"]).load_questions() '
     'if q["id"] == QUESTION_ID'),  # wc-question-head
    ('engine.py', '    refusal = "rule_not_committed" if not rule else',
     '    rule = rule or registry()[rule_id]\n    refusal = "rule_not_committed" if not rule else'),  # en-calib-rule
    # round 15: each deny alternative, killed by its own approved committed fixture (test_jev_platform_ask_denied.py DENIED)
    *[('ask.py', old, new) for old, new in [
        (r'(\.env[^/]*|', '('), ('(pem|', '('), ('|key|', '|'), ('|p12|', '|'), ('|pfx|', '|'), ('|kdbx|', '|'),
        ('|tfstate)', ')'), ('(id_rsa|', '('), ('|id_ed25519|', '|'), ('|credential|', '|'), ('|secret)', ')'),
        (r'|\.npmrc|', '|'), (r'|\.netrc|', '|'), (r'|\.pypirc)', ')'), (r'(\.git|', '('), (r'|\.hermes|', '|'),
        (r'|\.ssh|', '|'), (r'|\.aws|', '|'), (r'|\.vercel|', '|'), (r'|\.gcloud)', ')'),
        ('if _DENY_NAMES.search(rel) or sensitive(rel):', 'if _DENY_NAMES.search(rel):')]],
    # round 15: no inherited GIT_* variable chooses the repository (test_jev_platform_git_env.py)
    ('committed.py', ' if not k.startswith("GIT_")}', '}'),
    ('committed.py', 'stderr=subprocess.DEVNULL,\n                                      env=git_env(env))',
     'stderr=subprocess.DEVNULL,\n                                      env=env)'),
    ('committed.py', 'capture_output=True, text=True, env=git_env(env))', 'capture_output=True, text=True, env=env)'),
    # round 16: AAA compares the exact bytes verified; the receipt names that commit; no credential follows a redirect
    ('engine.py', '    commit = verified.resolve(ROOT)\n    try:',
     '    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,'
     ' text=True).stdout.strip()\n    try:'),  # test_jev_platform_binding_bytes.py receipt
    ('client.py', 'return urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout)',
     'return urllib.request.urlopen(req, timeout=timeout)'),
    ('client.py', 'return None  # answered as the HTTPError it is',
     'return super().redirect_request(req, fp, code, msg, headers, newurl)'),
    *[(f, 'with client.open_url(req, timeout) as resp:', 'with urllib.request.urlopen(req, timeout=timeout) as resp:')
      for f in ('__main__.py', 'gemini.py', 'evals/jev_constitution/harness.py')],
    # round 17: a symlink never chooses the committed path compared (test_jev_platform_binding_bytes.py)
    ('engine.py', '    bound = not linked and commit is not None and all(', '    bound = commit is not None and all('),
    ('engine.py', '[Path(os.path.abspath(p)) for p in paths]', '[p.resolve() for p in paths]'),
    # rounds 19-20: template ids and every decoded outbound string are screened (test_jev_platform_payload_screen.py)
    ('ask.py', ' or sensitive_payload({tid: q}):  # rounds 19-20', ':  # rounds 19-20'),
    ('ask.py', 'sensitive_payload(k) or sensitive_payload(v)', 'sensitive_payload(v)'),
    ('ask.py', '    if isinstance(obj, (list, tuple)):\n        return any(', '    if False:\n        return any('),
    *[(f, ' or ask.sensitive_payload(body):  # round 20', ':  # round 20') for f in ('scout.py', 'gemini.py')],
]
