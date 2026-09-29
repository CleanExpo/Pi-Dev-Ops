"""Mutation control for jev_platform: run `python tests/mutation/jev_platform_mutants.py`.

Break each guard once; the platform test suite must fail for every mutant."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
MUTANTS = [
    ("policy.py", "if not response_valid:", "if False:"),
    ("policy.py", "if state != USABLE_STATE or threshold is None:", "if threshold is None:"),
    ("policy.py", "if ABSTAIN_LOW <= noul <= ABSTAIN_HIGH:", "if False:"),
    ("policy.py", "if noul < FAIL_BELOW:", "if noul < 0.05:"),
    ("policy.py", "verdict = REFUSE if failing and not problems else ESCALATE",
     "verdict = REFUSE if failing and not problems else ('allow' if not reasons[:-1] else ESCALATE)"),
    ("policy.py", 'return "class_unverified"', 'return "class_ok"'),
    ("client.py", "if set(answers) != set(rule_ids):", "if not set(rule_ids) <= set(answers):"),
    ("client.py", "self.attempts >= self.max_attempts or ", ""),
    ("client.py", "or wait >= budget.remaining_seconds()", ""),
    ("client.py", "if len(json.dumps(body).encode()) > MAX_REQUEST_BYTES:", "if False:"),
    ("calibration.py", 'if valid_counts["v_missed"] or violations', "if violations"),
    ("calibration.py", "if record[\"bindings\"] != current_bindings:", "if False:"),
    ("calibration.py", "if cases_digest(scored) != record[\"cases_sha256\"]:", "if False:"),
    ("calibration.py", "valid = [c for c in scored if int(c[\"hash\"], 16) % 2 == 1]", "valid = scored"),
    ("engine.py", "if altered and result != policy.UNCERTAIN:", "if False:"),
    ("engine.py", "if errors or len(models) != 1:", "if len(models) > 1:"),
    ("engine.py", "if not all(p.resolve().is_relative_to(ROOT) for p in paths):", "if False:"),
    # release review r2 P1: a decision never relies on evidence that fails verification
    ("engine.py", 'return "corrupt" if problems else state', "return state"),
    ("engine.py", '    except (OSError, ValueError, KeyError, TypeError):\n        return "corrupt"',
     "    except (OSError, ValueError, KeyError, TypeError):\n        return state"),
    ("ask.py", "if digest != approved:", "if False:"),
    ("ask.py", "    if wrong_state:", "    if False:"),
    ("ask.py", "if not isinstance(approved, str):", "if False:"),
    ("ask.py", "q = _question(tid, t) if isinstance(t, dict) else None", "q = _question(tid, t or {'type': 'noul', 'question': 'x', 'true': 'y', 'false': 'z'})"),
    ("ask.py", '["git", "-C", repo, "show", f"HEAD:{MANIFEST}"]', '["cat", f"{repo}/{MANIFEST}"]'),
    ("ask.py", "nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)", "nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NONBLOCK, dir_fd=fd)"),
    ("ask.py", "leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)", "leaf = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK, dir_fd=fd)"),
    ("ask.py", "leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)", "leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)"),  # r7 FIFO
    ("ask.py", "    if sensitive(text):\n        return None, digest, \"sensitive content\"", "    if False:\n        return None, digest, \"sensitive content\""),
    ("ask.py", "if _DENY_NAMES.search(rel) or sensitive(rel):", "if False:"),
    ("ask.py", "if not isinstance(answers, dict) or set(answers) != set(questions):", "if not isinstance(answers, dict):"),
    ("ask.py", "if a.get(\"choice\") not in allowed or ", "if "),
    ("ask.py", "if len(set(template_ids)) != len(template_ids):", "if False:"),
    # Levels 9 and 10 (PLAN-scale.md rev 5)
    ("scout.py", 'matched = mf.expand(manifest["files"], patterns)',
     'matched = mf.expand([__import__("os").path.relpath(__import__("os").path.join(d, f), repo) '
     'for d, _, fs in __import__("os").walk(repo) for f in fs], patterns)'),
    ("manifest.py", 'text = manifest["prompts"].get(prompt_id)', 'text = manifest["prompts"].get(prompt_id, prompt_id)'),
    ("scout.py", 'body = {"state": _state(task, content), "model": MODEL, "questions": questions}',
     'body = {"state": {**_state(task, content), "note": " ".join(patterns)}, "model": MODEL, "questions": questions}'),
    ("ask.py", "env=git_env())", "env=dict(os.environ))"),
    ("scout.py", 'if a.get("choice") not in allowed or not set(probs) <= allowed:', "if False:"),
    ("scout.py", 'return {"outcome": "unavailable", "reason": "signal_unavailable:invalid_response"}',
     'return {"outcome": "none", "reason": "signal_unavailable:invalid_response"}'),
    ("scout.py", 'return {"outcome": "unavailable", "reason": sent.get("error", "signal_unavailable")}',
     'return {"outcome": "unavailable", "reason": sent.get("error", "signal_unavailable"), "confidence": 0.0, '
     '"probabilities": {}}'),
    ("scout.py", "if len(admitted) > MAX_SCOUT_FILES:", "if False:"),
    ("scout.py", "if len(json.dumps(body).encode()) > client.MAX_REQUEST_BYTES:", "if False:"),
    ("scout.py", "if ask.sensitive(json.dumps(body)):", "if False:"),
    ("manifest.py", "if reads not in ACCEPTS[tool]:", "if False:"),
    ("manifest.py", "    if missing:\n", "    if False:\n"),
    # Gemini runner (PLAN-scale.md rev 5)
    ("agent_tools.py", '    run.proposals.append(args)\n    return {"result": PROPOSED}',
     '    run.proposals.append(args)\n    run.jev_post({"state": {"task": str(args)}, "model": "jev-latest", '
     '"questions": {}}, 30)\n    return {"result": PROPOSED}'),
    ("agent_tools.py", 'base = {"path": r["path"]}', 'base = {"path": r["path"], "sha256": r["sha256"]}'),
    ("agent_tools.py", "    if extra:\n", "    if False:\n"),
    ("gemini.py", "        counted, problem, status = _count(count_url, payload, headers, budget, http_post)\n",
     "        counted, problem, status = len(payload) // 4, None, None\n"),
    ("gemini.py", "if self.batch_count_calls >= self.max_count_calls:", "if False:"),
    ("gemini.py", 'cost = nbytes * self.price["count"]', "cost = 0.0"),
    ("gemini.py", "        counted, problem, status = _count(count_url, payload, headers, budget, http_post)\n",
     "        budget.reserve_generate(len(payload) // 4)\n"
     "        counted, problem, status = _count(count_url, payload, headers, budget, http_post)\n"),
    # model chain: a quota refusal must advance; a locked run must never switch model
    ("gemini.py", "ADVANCE_STATUSES = (404, 429, 503)", "ADVANCE_STATUSES = ()"),
    ("gemini.py", "while (model := budget.model or next(", "while (model := None or next("),
    # carried thinking: the pre-send bound must include earlier thoughtsTokenCount
    ("gemini.py", "        bound = counted + carry  #", "        bound = counted  #"),
    ("gemini.py", "    carry = budget.thoughts if multi_turn else 0", "    carry = 0"),
    ("gemini.py", "    if multi_turn and not budget.thoughts_known:", "    if False:"),
    ("gemini.py", "                self.thoughts += t", "                self.thoughts += 0"),
    ("gemini.py", "    budget.add_thoughts(usage)\n", "\n"),
    # rev 6d: provider input ceiling for multi-turn, price check before every send, malformed thinking
    ("gemini.py", "reserve_generate(INPUT_TOKEN_LIMIT[model] if multi_turn else counted, price)", "reserve_generate(bound, price)"),
    ("gemini.py", "        if halt := _halt(model, budget):\n            return halt\n", "        if False:\n            return halt\n"),
    ("gemini.py", "        if halt := _halt(model, budget):  # the lock", "        if False:  # the lock"),
    ("gemini.py", "return ({\"error\": \"price table expired\"}, None) if price_table(today(), model) is None else None",
     "return None"),
    # release review r4 P1: a lock landing during count or between retries stops this model at once
    ("gemini.py", "    if budget.model not in (None, model):", "    if False:"),
    ("gemini.py", "with budget.selecting if budget.model is None else contextlib.nullcontext():",
     "with contextlib.nullcontext():"),  # r5 P1: one call at a time until a model is locked
    ("gemini_shape.py", "not in range(1, max_output_tokens + 1)", "not in range(1, 10**6)"),  # r6 P1: output bound
    ("gemini.py", "    body = json.loads(raw := json.dumps(body))", "    raw = json.dumps(body)"),  # r7 P1: private copy
    ("gemini.py", "if status not in ADVANCE_STATUSES and budget.model in (None, model):", "if status not in ADVANCE_STATUSES:"),
    ("gemini.py", "for v in (prompt, cands, thoughts))", "for v in (prompt, cands))"),
    ("gemini.py", "RUN_CAP_USD = 2.50", "RUN_CAP_USD = 1.00"),
    # release review P1s: per-model pricing, first-lock-wins, writer termination
    ("gemini.py", "INPUT_TOKEN_LIMIT[model] if multi_turn else counted, price)", "INPUT_TOKEN_LIMIT[model] if multi_turn else counted)"),
    ("gemini.py", "    budget.settle(reserved, usage, counted, price)", "    budget.settle(reserved, usage, counted)"),
    ("gemini.py", "            if self.model is None:\n                self.model, self.price", "            if True:\n                self.model, self.price"),
    ("evals/jev_constitution/generate.py", "            raise WriterExhausted(f\"gemini: {sent['error']}\")", "            raise ValueError(f\"gemini: {sent['error']}\")"),
    ("evals/jev_constitution/generate.py", "        if empty >= MAX_EMPTY_ROUNDS:", "        if False:"),
    ("gemini.py", "            budget.lock_model(model, price_table(on, model))\n", "            pass\n"),
    # release review r3 P1s: a lock landing mid-call, and no-progress writer rounds
    ("gemini.py", "            if budget.model != model:  #", "            if False:  #"),
    ("evals/jev_constitution/generate.py", "empty = 0 if have > before else empty + 1",
     "empty = 0 if any(t for _, t in batches) else empty + 1"),
    ("gemini.py", 'payload = json.dumps({**body, "model": f"models/{model}"}).encode()',
     "payload = json.dumps(body).encode()"),
    ("agent.py", '    ledger["agent_model"] = gem.model', '    ledger["agent_model"] = gemini.MODEL'),
    ("gemini.py", "        if prompt is None:\n            return\n",
     "        if prompt is None:\n            self.spent -= reserved\n            return\n"),
    ("gemini.py", "if isinstance(prompt, int) and prompt > counted:", "if False:"),
    ("gemini.py", 'if p is None or on > dt.date.fromisoformat(p["valid_until"]):', "if p is None:"),
    ("agent.py", 'ledger.update({"jev_calls": len(run.sends),',
     'ledger.update({"jev_calls": sum(run.tool_calls.get(t, 0) for t in agent_tools.JEV_TOOLS),'),
    # Gemini writer control: each verdict clause, and the code-computed anchor
    ("evals/jev_constitution/writer_control.py", 'if not gem["agreement"] >= AGREE_FLOOR - 1e-9:', "if False:"),
    ("evals/jev_constitution/writer_control.py",
     'if not gem["agreement"] >= claude["agreement"] - AGREE_MARGIN - 1e-9:', "if False:"),
    ("evals/jev_constitution/writer_control.py",
     'if not all(gem["admitted_by_class"].get(c, 0) >= MIN_ADMITTED for c in FAILURE_CLASSES):', "if False:"),
    ("evals/jev_constitution/writer_control.py",
     'if not (gem["anchor_accuracy"] >= ANCHOR_FLOOR - 1e-9 and gem["anchor_accuracy"] >= claude["anchor_accuracy"]):',
     "if False:"),
    ("evals/jev_constitution/writer_control.py", "round(num / den * 100, 1) == round(claim, 1)", "True"),
    # release review r8 P1s: unpriced generation settings, and the writer control enforced at the CLI
    ("gemini_shape.py", 'set(cfg) != {"maxOutputTokens", "thinkingConfig"}', 'not set(cfg) >= {"maxOutputTokens", "thinkingConfig"}'),
    ("gemini.py", "    if refusal := gemini_shape.problem(body, MAX_OUTPUT_TOKENS, THINKING_LEVEL):", "    if refusal := None:"),
    ("gemini_shape.py", "    if extra := set(body) - TOP_LEVEL:", "    if extra := None:"),
    ("gemini_shape.py", 'set(t) == {"functionDeclarations"}', '"functionDeclarations" in t'),
    ("gemini_shape.py", 'c["role"] in ROLES and _parts_ok(c["parts"], PART_KEYS)', 'c["role"] in ROLES'),
    ("gemini_shape.py", 'or cfg["thinkingConfig"] != {"thinkingLevel": thinking_level}:', ":"),
    ("gemini_shape.py", ' or isinstance(cfg["maxOutputTokens"], bool)', ""),
    ("gemini_shape.py", '_parts_ok(body["systemInstruction"]["parts"], {"text"})', "True"),
    ("gemini_shape.py", '    if "model" in body and not isinstance(body["model"], str):', "    if False:"),
    # release review r9: the traversal guard reached directly, and live decide on the committed fixture only
    ("ask.py", 'if rel.startswith("/") or any(p in ("", ".", "..") for p in parts):', "if False:"),
    ("evals/jev_constitution/generate.py", "json.loads(shown.stdout) if shown.returncode == 0 else {}",
     "json.loads(WRITER_CONTROL.read_text())"),  # the writer control counts only as committed
    ("__main__.py", "    actions = _committed_actions() if a.live else",
     '    actions = json.loads(engine.FIXTURES.read_text())["actions"] if a.live else'),
    ("evals/jev_constitution/generate.py", '!= ("run", "use"):', '!= ("run", "use") and False:'),
    ("evals/jev_constitution/generate.py", '(control.get("status"), control.get("verdict")) != ("run", "use")',
     'control.get("verdict") != "use"'),
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
    ('engine.py', 'return ("AAA", []) if tracked and clean else',
     'return ("AAA", []) if clean else'),  # en-rating-tracked
    ('engine.py', 'return ("AAA", []) if tracked and clean else',
     'return ("AAA", []) if tracked else'),  # en-rating-clean
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
     '        if mode != "120000":',
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
]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def suite() -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                           *map(str, (ROOT / "tests").glob("test_jev_platform_*.py"))],
                          cwd=ROOT, capture_output=True, text=True, env=env)


# A red suite "kills" every mutant, so the count means nothing unless the unmutated suite is green first
# (e.g. a copy without .git fails every committed-file test). Positive control, then the mutants.
baseline = suite()
if baseline.returncode != 0:
    print("BASELINE RED: the unmutated suite fails, so no mutant result is evidence\n" + baseline.stdout[-2000:])
    sys.exit(2)
killed = 0
for fname, old, new in MUTANTS:
    path = ROOT / fname if "/" in fname else ROOT / "jev_platform" / fname
    src = path.read_text()
    assert src.count(old) == 1, (fname, old)
    path.write_text(src.replace(old, new))
    try:
        r = suite()
    finally:
        path.write_text(src)
    ok = r.returncode != 0
    killed += ok
    print(("KILLED  " if ok else "SURVIVED"), fname, "|", old[:60])
print(f"{killed}/{len(MUTANTS)} mutants killed")
sys.exit(0 if killed == len(MUTANTS) else 1)
