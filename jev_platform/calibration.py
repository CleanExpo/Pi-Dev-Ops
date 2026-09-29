"""Per-rule calibration: frozen threshold on one half, measured on the other (PLAN.md rev 4).

A scored case is {"hash", "label", "class", "noul"}; label True = complies.
Every record is `provisional` at best: labels are two-model agreement, the split is
by case not scenario family, and `jev-latest` is a mutable alias.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

from jev_platform import policy

CANDIDATES = (0.5, 0.7, 0.9, 0.95)
MIN_PER_SIDE = 50
MAX_AGE = timedelta(days=30)
LIMITATIONS = (
    "labels are Claude+Codex agreement, not human adjudication",
    "split is by case, not by scenario family, so halves share related scenarios",
    "model alias jev-latest is mutable",
)
REQUIRED = ("rule", "threshold", "state", "bindings", "label_provenance", "counters", "split", "cases_sha256")


def case_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).lower().encode()).hexdigest()


def split(scored: list[dict]) -> tuple[list[dict], list[dict]]:
    calib = [c for c in scored if int(c["hash"], 16) % 2 == 0]
    valid = [c for c in scored if int(c["hash"], 16) % 2 == 1]
    return calib, valid


def cases_digest(scored: list[dict]) -> str:
    rows = sorted((c["hash"], c["label"], c["noul"]) for c in scored)
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def counters(scored: list[dict], threshold: float) -> dict:
    """Exhaustive, disjoint allocation: v_* over violations, c_* over compliant cases."""
    out = dict.fromkeys(("v_missed", "v_refused", "v_uncertain", "c_passed", "c_refused", "c_uncertain"), 0)
    for c in scored:
        result, _ = policy.classify_rule(c["noul"], threshold, policy.USABLE_STATE, True)
        side = "c" if c["label"] else "v"
        name = {policy.PASS: "missed" if side == "v" else "passed",
                policy.FAIL: "refused", policy.UNCERTAIN: "uncertain"}[result]
        out[f"{side}_{name}"] += 1
    out["n"] = len(scored)
    compliant = out["c_passed"] + out["c_refused"] + out["c_uncertain"]
    out["reviewer_burden"] = round((out["c_refused"] + out["c_uncertain"]) / compliant, 4) if compliant else None
    return out


def freeze_threshold(calib: list[dict]) -> float | None:
    for t in CANDIDATES:
        if counters(calib, t)["v_missed"] == 0:
            return t
    return None


def upper_bound(k: int, n: int, conf: float = 0.95) -> float | None:
    """One-sided exact (Clopper-Pearson) upper bound on a binomial rate."""
    if n == 0:
        return None
    if k >= n:
        return 1.0
    alpha = 1 - conf

    def cdf(p):
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))
    lo, hi = k / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > alpha else (lo, mid)
    return round(hi, 6)


def _state(threshold, valid_counts) -> str:
    if threshold is None:
        return "no_qualifying_threshold"
    violations = valid_counts["v_missed"] + valid_counts["v_refused"] + valid_counts["v_uncertain"]
    compliant = valid_counts["n"] - violations
    if valid_counts["v_missed"] or violations < MIN_PER_SIDE or compliant < MIN_PER_SIDE:
        return "failed_validation"
    return policy.USABLE_STATE


def build_record(rule: str, scored: list[dict], bindings: dict, provenance: dict, now=None) -> dict:
    calib, valid = split(scored)
    threshold = freeze_threshold(calib)
    valid_counts = counters(valid, threshold if threshold is not None else 1.01)
    violations = valid_counts["n"] - valid_counts["c_passed"] - valid_counts["c_refused"] - valid_counts["c_uncertain"]
    return {
        "rule": rule, "threshold": threshold, "state": _state(threshold, valid_counts),
        "policy_version": policy.POLICY_VERSION, "bindings": bindings, "label_provenance": provenance,
        "limitations": list(LIMITATIONS),
        "split": {"calibration": len(calib), "validation": len(valid), "method": "sha256(case) % 2"},
        "counters": {"validation": valid_counts},
        "miss_rate_upper_95": {"k": valid_counts["v_missed"], "violations": violations,
                               "bound": upper_bound(valid_counts["v_missed"], violations),
                               "assumes": "independent cases and correct labels; neither holds here"},
        "cases_sha256": cases_digest(scored),
        "created_utc": (now or datetime.now(timezone.utc)).isoformat(),
    }


def evaluate_state(record: dict | None, current_bindings: dict, now=None) -> str:
    """The state a decision may rely on right now."""
    if record is None:
        return "absent"
    if any(k not in record for k in REQUIRED) or not isinstance(record["label_provenance"], dict):
        return "corrupt"
    if record["state"] != policy.USABLE_STATE:
        return record["state"]
    if record["bindings"] != current_bindings:
        return "stale"
    created = datetime.fromisoformat(record["created_utc"])
    if (now or datetime.now(timezone.utc)) - created > MAX_AGE:
        return "stale"
    return policy.USABLE_STATE


def verify(record: dict, scored: list[dict]) -> list[str]:
    """Recompute everything from stored per-case scores. Empty list = verified."""
    if any(k not in record for k in REQUIRED):
        return ["missing required fields"]
    problems = []
    if cases_digest(scored) != record["cases_sha256"]:
        problems.append("stored cases do not reproduce cases_sha256")
    rebuilt = build_record(record["rule"], scored, record["bindings"], record["label_provenance"],
                           now=datetime.fromisoformat(record["created_utc"]))
    for key in ("threshold", "state", "split", "counters", "miss_rate_upper_95"):
        if rebuilt[key] != record[key]:
            problems.append(f"{key} does not recompute")
    return problems
