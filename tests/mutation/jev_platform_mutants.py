"""Mutation control for jev_platform: run `python tests/mutation/jev_platform_mutants.py`.

Break each guard once; the platform test suite must fail for every mutant."""
import concurrent.futures
import contextlib
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from jev_platform_guard_mutants import GUARD_MUTANTS

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
    ("ask.py", 'found = verified.at_head(repo, MANIFEST, env=git_env())', 'found = ("", "", open(f"{repo}/{MANIFEST}", "rb").read())'),
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
    ("evals/jev_constitution/generate.py", "json.loads(shown) if shown is not None else {}",
     "json.loads(WRITER_CONTROL.read_text())"),  # the writer control counts only as committed
    ("__main__.py", "    actions = _committed_actions() if a.live else",
     '    actions = json.loads(engine.FIXTURES.read_text())["actions"] if a.live else'),
    ("evals/jev_constitution/generate.py", '!= ("run", "use"):', '!= ("run", "use") and False:'),
    ("evals/jev_constitution/generate.py", '(control.get("status"), control.get("verdict")) != ("run", "use")',
     'control.get("verdict") != "use"'),
]
MUTANTS += GUARD_MUTANTS
# Wall-clock-bounded tests (engineering.md, Concurrency): a kill by one is re-run alone; passing -> SURVIVED.
WALL_CLOCK = {
    "tests/test_jev_platform_ask.py::test_a_fifo_at_an_admitted_path_is_refused_without_blocking",
    "tests/test_jev_platform_gemini_lock.py::test_while_no_model_is_locked_a_second_call_sends_nothing_until_the_first_settles"}
BASELINE_CEILING, BUDGET = 300, 900
LABEL = {"killed": "KILLED  ", "survived": "SURVIVED", "timeout": "TIMEOUT "}
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
_running: dict = {}  # pid -> live suite process, so every exit path can kill its process group
class Refusal(Exception):
    """A failed control: diagnostic to stderr, exit 2, and never a certificate line."""
def git(*args, cwd=ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
def _kill(proc) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
def suite(clone: Path, basetemp: str, timeout: float) -> tuple[int | None, str]:  # rc None = timed out
    tests = sorted(f"tests/{p.name}" for p in (clone / "tests").glob("test_jev_platform_*.py"))  # ids match WALL_CLOCK
    proc = subprocess.Popen([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", f"--basetemp={basetemp}", *tests],
                            cwd=clone, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    _running[proc.pid] = proc
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        _kill(proc)  # the whole process group, so no grandchild outlives the verdict
        proc.communicate()
        return None, ""
    finally:
        _running.pop(proc.pid, None)
def clean(clone: Path) -> bool:  # tracked, untracked and ignored residue all count
    r = git("status", "--porcelain", "--untracked-files=all", "--ignored", cwd=clone)
    return r.returncode == 0 and r.stdout == ""
def baselines(pool, clones, basetemps, timeout: float, label: str) -> float:  # all clones at once; slowest wall
    def one(k):
        start = time.monotonic()
        rc, out = suite(clones[k], basetemps[k], timeout)
        if rc != 0:
            raise Refusal(f"BASELINE TIMEOUT{label}: {clones[k]} exceeded {timeout:.0f}s" if rc is None
                          else f"BASELINE RED{label}: {clones[k]} rc={rc}\n{out[-2000:]}")
        return time.monotonic() - start
    return max(f.result() for f in [pool.submit(one, k) for k in range(len(clones))])
def mutate(i: int, clone: Path, basetemp: str, timeout: float) -> tuple:  # (outcome, rc, killer, seconds)
    fname, old, new = MUTANTS[i]
    if not clean(clone):
        raise Refusal(f"DIRTY CLONE before mutant {i}: {clone}")
    path = clone / fname if "/" in fname else clone / "jev_platform" / fname
    src = path.read_text()
    if src.count(old) != 1:
        raise Refusal(f"RUNNER ERROR: mutant {i} anchor matches {src.count(old)} times in {fname}")
    path.write_text(src.replace(old, new))
    start = time.monotonic()
    try:
        rc, out = suite(clone, basetemp, timeout)
    finally:
        path.write_text(src)
    if not clean(clone):
        raise Refusal(f"DIRTY CLONE after mutant {i}: {clone}\n{git('status', '--porcelain', '--ignored', cwd=clone).stdout}")
    killer = re.search(r"^(?:FAILED|ERROR) (tests/\S+)", out, re.M) if rc == 1 else None
    if rc not in (None, 0, 1) or (rc == 1 and not killer):  # a kill must name its test, or WALL_CLOCK is blind
        raise Refusal(f"RUNNER ERROR: mutant {i} ({fname}) pytest rc={rc} (unexpected rc, or rc=1 naming no tests/ id)\n{out[-2000:]}")
    outcome = "timeout" if rc is None else "killed" if rc == 1 else "survived"
    return outcome, rc, killer.group(1) if killer else None, time.monotonic() - start
def emit(results: dict, printed: int, hold: set) -> int:  # result lines in index order, once each is final
    while printed in results and printed not in hold:
        print(LABEL[results[printed][0]], MUTANTS[printed][0], "|", MUTANTS[printed][1][:60], flush=True)
        printed += 1
    return printed
def run(clones: list, basetemps: list, pool) -> int:
    t0 = time.monotonic()
    timeout = max(120.0, 5 * baselines(pool, clones, basetemps, BASELINE_CEILING, ""))
    print(f"workers={len(clones)} head={SHA} timeout={timeout:.0f}s", file=sys.stderr, flush=True)
    free, errors = queue.Queue(), []
    list(map(free.put, range(len(clones))))
    def task(i):
        k = free.get()
        if k is None:  # an earlier task failed and kept its clone: wake the next waiter, report that failure
            free.put(None)
            raise errors[0]
        try:
            result = mutate(i, clones[k], basetemps[k], timeout)
        except BaseException as e:
            errors.append(e)
            free.put(None)
            raise
        free.put(k)  # only a clone that came back byte-clean is re-queued
        return k, result  # the clone it ran in, so a wall-clock rerun uses the same one
    results, where, printed, rerun = {}, {}, 0, set()
    futures = {pool.submit(task, i): i for i in range(len(MUTANTS))}
    for f in concurrent.futures.as_completed(futures):
        i = futures[f]
        k, (outcome, rc, killer, secs) = where[i], results[i] = f.result()
        if killer and killer.split("[")[0] in WALL_CLOCK:
            rerun.add(i)  # rerun in clone where[i], alone
        print(f"[{len(results)}/{len(MUTANTS)}] {LABEL[outcome].strip()} idx={i} {MUTANTS[i][0]} {secs:.1f}s {killer or f'rc={rc}'}", file=sys.stderr, flush=True)
        printed = emit(results, printed, rerun)
    for i in sorted(rerun):  # alone: no other suite is running now
        results[i] = mutate(i, clones[where[i]], basetemps[where[i]], timeout)
        print(f"RERUN idx={i} {results[i][0]} {results[i][2] or f'rc={results[i][1]}'}", file=sys.stderr, flush=True)
    emit(results, printed, set())
    baselines(pool, clones, basetemps, min(BASELINE_CEILING, timeout), " (closing)")
    killed = sum(1 for r in results.values() if r[0] == "killed")
    print(f"elapsed={time.monotonic() - t0:.0f}s budget={BUDGET}s", file=sys.stderr, flush=True)
    print(f"{killed}/{len(MUTANTS)} mutants killed", flush=True)  # last, and only after every control passed
    return 0 if killed == len(MUTANTS) else 1
def main() -> int:
    global SHA
    SHA = git("rev-parse", "--verify", "HEAD").stdout.strip()
    untracked = git("ls-files", "--others", "--exclude-standard", "--", "jev_platform", "evals", "tests").stdout
    if len(SHA) != 40 or git("diff", "--quiet", SHA, "--", "jev_platform", "evals", "tests").returncode or untracked:
        print(f"DIRTY TREE: {ROOT} differs from HEAD {SHA or '?'} under jev_platform/, evals/ or tests/; commit first. Nothing was run.", file=sys.stderr)
        return 2
    jobs = int(os.environ.get("JEV_MUT_JOBS") or min(4, os.cpu_count() or 1))
    clones, basetemps, code = [], [], 2
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=jobs)
    try:
        for _ in range(jobs):
            clones.append(Path(tempfile.mkdtemp(prefix="jev-mut-")))
            basetemps.append(tempfile.mkdtemp(prefix="jev-mut-bt-"))
            for args in (["clone", "--shared", "--quiet", "--no-checkout", str(ROOT), str(clones[-1])],
                         ["-C", str(clones[-1]), "checkout", "--quiet", "--detach", SHA]):
                r = subprocess.run(["git", *args], capture_output=True, text=True)
                if r.returncode != 0:
                    raise Refusal(f"CLONE FAILED: git {' '.join(args[:2])}: {r.stderr.strip()}")
        code = run(clones, basetemps, pool)
    except Exception as e:  # the first failure is reported as itself, never a cleanup error
        print(str(e) if isinstance(e, Refusal) else f"RUNNER ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    finally:  # stop queued work, kill running suites so the wait is short, then remove every temp dir
        pool.shutdown(wait=False, cancel_futures=True)
        for proc in list(_running.values()):
            _kill(proc)
        pool.shutdown(wait=True)
        for d in [*clones, *basetemps]:
            shutil.rmtree(d, ignore_errors=True)
    return code

if __name__ == "__main__":
    sys.exit(main())
