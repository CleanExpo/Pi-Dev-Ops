"""Prove mode's scripts give the decisions the verdict rules promise. Offline: no network, no keys.

Each test pins one rule from references/prove-mode.md, so loosening the rule in a script fails here.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args, stdin=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          input=stdin, timeout=60)


def board(rows):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    out = run(HERE / "prove_scoreboard.py", f.name, "--json")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def verdict(i, overall):
    return {"id": f"c{i}", "overall": overall, "criteria": {"accuracy": overall}, "challenger_defects": []}


def test_fewer_than_eight_cases_is_not_evidence():
    b = board([verdict(i, "challenger") for i in range(7)])
    assert b["decision"].startswith("not enough evidence"), b


def test_two_to_one_wins_is_a_ship_candidate():
    b = board([verdict(i, "challenger") for i in range(8)] + [verdict(9, "current")])
    assert b["overall"] == [8, 1, 0] and b["decision"].startswith("ship candidate"), b


def test_close_result_is_not_a_ship():
    b = board([verdict(i, "challenger") for i in range(5)] + [verdict(i, "current") for i in range(5, 9)])
    assert not b["decision"].startswith("ship"), b


def test_order_disagreement_is_a_tie():
    """The mock judge always picks A, so the two orders disagree and every case must tie."""
    with tempfile.TemporaryDirectory() as t:
        cases = Path(t) / "cases.jsonl"; out = Path(t) / "v.jsonl"
        cases.write_text("".join(json.dumps({"id": f"c{i}", "task": "t", "context": "x",
                                             "criteria": [{"key": "accuracy", "description": "d"}],
                                             "current": "a", "challenger": "b"}) + "\n" for i in range(8)))
        r = run(HERE / "prove_judge.py", cases, "--out", out, "--provider", "mock")
        assert r.returncode == 0, r.stderr
        rows = [json.loads(l) for l in out.read_text().splitlines()]
        assert len(rows) == 8 and all(x["overall"] == "tie" and not x["consistent"] for x in rows), rows


def test_judge_refuses_to_run_without_a_model():
    with tempfile.TemporaryDirectory() as t:
        cases = Path(t) / "c.jsonl"; cases.write_text("")
        r = run(HERE / "prove_judge.py", cases, "--out", Path(t) / "v.jsonl", "--provider", "openrouter")
        assert r.returncode != 0 and "--model is required" in (r.stderr + r.stdout)


def test_quote_check_catches_an_invented_quote():
    with tempfile.TemporaryDirectory() as t:
        corpus = Path(t) / "src.txt"; corpus.write_text("The meeting moved to Tuesday at 10am.")
        quotes = Path(t) / "q.txt"; quotes.write_text("moved to Tuesday\nmoved to Friday\n")
        r = run(HERE / "prove_checks.py", "quotes", quotes, "--corpus", corpus, "--json")
        data = json.loads(r.stdout)
        text = json.dumps(data)
        assert "Friday" in text and r.returncode != 0, (r.returncode, data)


def test_mostly_ties_is_not_a_ship():
    b = board([verdict(i, "challenger") for i in range(2)] + [verdict(i, "tie") for i in range(2, 10)])
    assert b["overall"] == [2, 0, 8] and b["decision"].startswith("mostly ties"), b


def _judge_module():
    spec = importlib.util.spec_from_file_location("prove_judge", HERE / "prove_judge.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_malformed_judge_replies_are_rejected():
    j = _judge_module()
    good = {"criteria": {"accuracy": {"winner": "A", "reason": "r"}}, "overall": "B",
            "overall_reason": "r", "defects_A": [], "defects_B": ["d"]}
    assert j.validate(json.loads(json.dumps(good)), ["accuracy"]) == good
    bad_cases = [
        {**good, "criteria": {"accuracy": {"winner": "INVALID", "reason": "r"}}},
        {**good, "criteria": {"accuracy": {"winner": "A"}}},
        {**good, "criteria": {}},
        {**good, "overall": "C"},
        {**good, "defects_A": "not a list"},
        {**good, "defects_B": [1]},
        {**good, "extra": 1},
    ]
    for case in bad_cases:
        try:
            j.validate(case, ["accuracy"])
        except RuntimeError:
            continue
        raise AssertionError(f"accepted malformed reply {case}")
    try:
        j.to_side("INVALID", True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("to_side accepted an unknown verdict")


if __name__ == "__main__":  # run-estate-checks runs this file directly: every test must execute
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001 - report every failure, then exit non-zero
            failed += 1
            print(f"FAIL {name}\n{traceback.format_exc()}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
