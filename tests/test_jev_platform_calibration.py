"""Offline controls for jev_platform.calibration (PLAN.md rev 4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jev_platform import calibration as c

B = {"rule_text": "r1", "model": "jev-latest", "eval_sha": "abc"}
PROV = {"writer": "claude sonnet", "labeller": "codex", "procedure": "agreement only", "adjudication": "none"}
NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def cases(n=400, violation_noul=0.02, compliant_noul=0.97):
    out = []
    for i in range(n):
        label = i % 2 == 0
        out.append({"hash": c.case_hash(f"case {i}"), "label": label, "class": "normal",
                    "noul": compliant_noul if label else violation_noul})
    return out


def test_split_is_deterministic_and_disjoint():
    s = cases()
    a1, b1 = c.split(s)
    a2, b2 = c.split(list(reversed(s)))
    assert {x["hash"] for x in a1} == {x["hash"] for x in a2}
    assert not {x["hash"] for x in a1} & {x["hash"] for x in b1} and len(a1) + len(b1) == len(s)
    assert {x["hash"] for x in b1} == {x["hash"] for x in b2}


def test_counters_are_exhaustive():
    s = cases()
    s[0]["noul"], s[1]["noul"], s[3]["noul"] = 0.5, 0.95, 0.5
    k = c.counters(s, 0.9)
    assert sum(k[x] for x in k if x[:2] in ("v_", "c_")) == k["n"] == 400
    assert k["v_missed"] == 1 and k["v_uncertain"] == 1 and k["c_uncertain"] == 1


def test_freeze_uses_lowest_zero_miss_threshold():
    s = cases()
    s[1]["noul"] = 0.8  # one violation passes at 0.5 and 0.7
    assert c.freeze_threshold(s) == 0.9
    s[1]["noul"] = 0.99
    assert c.freeze_threshold(s) is None


def test_upper_bound_exact_clopper_pearson():
    assert abs(c.upper_bound(0, 50) - 0.058155) < 1e-5  # 1 - 0.05**(1/50), not 3/50
    assert abs(c.upper_bound(0, 100) - (1 - 0.05 ** (1 / 100))) < 1e-5
    ub = c.upper_bound(2, 100)
    cdf = sum(c.math.comb(100, i) * ub ** i * (1 - ub) ** (100 - i) for i in range(3))
    assert ub > 0.02 and abs(cdf - 0.05) < 1e-4
    assert c.upper_bound(0, 0) is None and c.upper_bound(5, 5) == 1.0


def test_clean_record_is_provisional_and_verifies():
    s = cases()
    r = c.build_record("r1", s, B, PROV, now=NOW)
    assert r["state"] == "provisional" and r["threshold"] == 0.5
    assert c.verify(r, s) == []
    assert c.evaluate_state(r, B, now=NOW) == "provisional"


def test_validation_miss_fails_the_rule():
    s = cases()
    _, valid = c.split(s)
    next(x for x in valid if not x["label"])["noul"] = 0.99
    assert c.build_record("r1", s, B, PROV, now=NOW)["state"] == "failed_validation"


def test_too_few_violation_cases_fails_the_rule():
    s = [x for x in cases() if x["label"]] + [x for x in cases() if not x["label"]][:40]
    assert c.build_record("r1", s, B, PROV, now=NOW)["state"] == "failed_validation"


def test_states_absent_corrupt_stale():
    r = c.build_record("r1", cases(), B, PROV, now=NOW)
    assert c.evaluate_state(None, B) == "absent"
    assert c.evaluate_state({k: v for k, v in r.items() if k != "label_provenance"}, B, now=NOW) == "corrupt"
    assert c.evaluate_state(r, {**B, "model": "jev-2"}, now=NOW) == "stale"
    assert c.evaluate_state(r, B, now=NOW + timedelta(days=31)) == "stale"


def test_verify_catches_tampered_scores_and_counters():
    s = cases()
    r = c.build_record("r1", s, B, PROV, now=NOW)
    s[1]["noul"] = 0.9
    assert "stored cases do not reproduce cases_sha256" in c.verify(r, s)
    s[1]["noul"] = 0.02
    r["counters"]["validation"]["v_missed"] = 0 if r["counters"]["validation"]["v_missed"] else 1
    assert "counters does not recompute" in c.verify(r, s)
