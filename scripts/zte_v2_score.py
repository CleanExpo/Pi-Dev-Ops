"""
zte_v2_score.py — Compute ZTE Framework v2 Section C scores from live data.

Reads from:
  - Supabase gate_checks table (C1: deployment success, C3: mean time to value)
  - .harness/scan-results/ (C4: security posture)
  - .harness/lessons.jsonl (C5: knowledge accumulation velocity)
  - C2 (output acceptance) is stubbed — requires Linear state-transition data
    that will be collected once RA-672 Phase 2 (Linear webhook event logging) lands.

Usage:
    python scripts/zte_v2_score.py [--json] [--days 30]

Output:
    Prints a human-readable v2 score card, or JSON with --json.
    Writes .harness/zte-v2-score.json for board meeting Phase 1 consumption.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

_HARNESS = Path(__file__).parent.parent / ".harness"
_OUTPUT = _HARNESS / "zte-v2-score.json"
_REPO_ROOT = Path(__file__).parent.parent


def _load_env_file() -> None:
    """Load .env from repo root when Supabase vars are absent from the environment.

    Runs at import time so the scorer works on Mac Mini dev without any manual
    `source .env` step. Uses stdlib only — no python-dotenv dependency.
    """
    if os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL"):
        return  # already present — nothing to do
    env_file = _REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_env_file()


# ─── data sources ─────────────────────────────────────────────────────────────

def _supabase_query(table: str, select: str, filters: str = "") -> list[dict]:
    """Query Supabase REST API. Returns [] on any error."""
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return []
    # Supabase REST: percent-encode '+' in ISO timestamps so timezone offset
    # "+00:00" isn't treated as a space by the HTTP layer.
    safe_filters = filters.replace("+", "%2B")
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}?select={select}"
    if safe_filters:
        endpoint += f"&{safe_filters}"
    req = urllib.request.Request(
        endpoint,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return []


def _load_outcomes_as_gate_rows(days: int = 30) -> list[dict]:
    """Local fallback: read session-outcomes.jsonl as gate_checks-compatible rows.

    Used when Supabase credentials are absent (e.g. Mac Mini dev environment).
    Returns rows in the same shape that score_c1/c3/c5 expect from Supabase.
    """
    outcomes_file = _HARNESS / "session-outcomes.jsonl"
    if not outcomes_file.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    try:
        with open(outcomes_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts_str = entry.get("checked_at") or entry.get("completed_at", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                    rows.append({
                        "shipped":             entry.get("shipped", entry.get("push_ok", False)),
                        "review_score":        entry.get("review_score", 0),
                        "session_started_at":  entry.get("session_started_at"),
                        "push_timestamp":      entry.get("push_timestamp"),
                        "checked_at":          ts_str,
                    })
                except Exception:
                    pass
    except Exception:
        return []
    return rows


def _load_scanner_summary() -> list[dict]:
    """Load latest scan results from .harness/scan-results/ JSON files.

    Reads each <project>/<date>-<scan_type>.json file directly — no async
    scanner import required.  Returns a list of project dicts compatible with
    score_c4_security_posture(): [{"project_id": ..., "scores": {...}}]
    """
    scan_root = _HARNESS / "scan-results"
    if not scan_root.is_dir():
        return []
    projects: dict[str, dict[str, int]] = {}
    for proj_dir in scan_root.iterdir():
        if not proj_dir.is_dir():
            continue
        proj_id = proj_dir.name
        for scan_type in ("security", "code_quality", "dependencies", "deployment_health"):
            files = sorted(proj_dir.glob(f"*-{scan_type}.json"))
            if not files:
                continue
            try:
                data = json.loads(files[-1].read_text(encoding="utf-8"))
                score = data.get("score") if data.get("score") is not None else data.get("health_score")
                if score is not None:
                    projects.setdefault(proj_id, {})[scan_type] = int(score)
            except Exception:
                pass
    return [{"project_id": k, "scores": v} for k, v in projects.items()]


def _lessons_per_week(days: int = 30) -> float:
    """Return average lessons added per week over the last `days` days."""
    lessons_file = _HARNESS / "lessons.jsonl"
    if not lessons_file.exists():
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    try:
        with open(lessons_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry.get("ts", "").replace("Z", "+00:00"))
                    if ts >= cutoff:
                        count += 1
                except Exception:
                    pass
    except Exception:
        return 0.0
    weeks = days / 7
    return count / weeks if weeks else 0.0


# ─── scoring functions ────────────────────────────────────────────────────────

#: Minimum attributed reverts before C1 reports a rate (see score_c1).
_C1_MIN_ATTRIBUTED = 5
#: Minimum attribution coverage before C1 reports a rate.
_C1_MIN_COVERAGE = 0.5


def score_c1_deployment_success(rows: list[dict], days: int = 30) -> tuple[int, str]:
    """C1: observed rollback rate over changes Pi-CEO shipped.

    RA-7216 gap 2. This previously scored `shipped/total` and reported it as a
    24-hour survival rate — the construction the ticket's first guardrail names
    as forbidden, because a ship rate says nothing about what happened after the
    ship. It then returned `needs_data` at every rate while the telemetry was
    built. It now reads real revert events.

    Deliberately NOT named "% surviving 24h". Silent defects, forward fixes and
    non-Pi-CEO changes are all invisible to any passive signal, so this measures
    OBSERVED rollbacks of ATTRIBUTED changes — a floor, not the true rate. The
    honest name is what stops it being read as the thing it is not.

    Per the §9 decision (option b, 14/08/2026) the unattributed count is
    reported beside the rate and never folded into it, and coverage is surfaced
    explicitly — a healthy-looking rate computed over three attributed reverts
    while forty went unattributed reads as reassurance when it is the opposite.
    Below either floor the rate degrades to `needs_data` rather than reporting
    confidently over a small attributed slice.

    `re_land` (a revert of a revert) is excluded from the numerator: it re-lands
    the original change, and counting it would double-penalise the recovery.
    """
    merged = [r for r in rows if r.get("merge_sha")]
    events = _fetch_outcome_events("revert", days)
    attributed = [e for e in events if e.get("gate_check_id") is not None]
    unattributed = len(events) - len(attributed)

    if not merged:
        return 1, "needs_data — no merged changes in window to measure against"

    total_events = len(attributed) + unattributed
    coverage = (len(attributed) / total_events) if total_events else 1.0
    suffix = (
        f"unattributed_reverts={unattributed}; "
        f"attribution_coverage={coverage:.0%}"
    )

    if len(attributed) < _C1_MIN_ATTRIBUTED:
        return 1, (
            f"needs_data — only {len(attributed)} attributed revert(s), below the "
            f"{_C1_MIN_ATTRIBUTED}-event floor; {suffix} [DIAGNOSTIC ONLY]"
        )
    if coverage < _C1_MIN_COVERAGE:
        return 1, (
            f"needs_data — attribution coverage {coverage:.0%} below "
            f"{_C1_MIN_COVERAGE:.0%}; a rate over {len(attributed)} attributed "
            f"reverts would misrepresent {unattributed} unattributed; {suffix}"
        )

    rate = len(attributed) / len(merged)
    note = (
        f"observed_rollback_rate={len(attributed)}/{len(merged)} ({rate:.0%}) "
        f"of merged changes reverted; {suffix}"
    )
    # Lower rollback rate is better, so the bands invert relative to the others.
    if rate <= 0.02:
        return 5, note
    if rate <= 0.05:
        return 4, note
    if rate <= 0.10:
        return 3, note
    if rate <= 0.20:
        return 2, note
    return 1, note


def _fetch_outcome_events(kind: str, days: int) -> list[dict]:
    """Return outcome_events of one kind inside the window. [] on any failure."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return _supabase_query(
        "outcome_events",
        "kind,gate_check_id,merge_sha,occurred_at",
        f"kind=eq.{kind}&occurred_at=gte.{cutoff}&limit=500",
    )


#: Minimum terminal outcomes before C2 reports a real score (see _score_from_rows).
_C2_MIN_SAMPLE = 5


def score_c2_output_acceptance(days: int = 30) -> tuple[int, str]:
    """C2: % of terminal outcomes that were acceptances.

    RA-7216 rewrote this. It previously had three defects, all measured:

    1. It counted "In Review" as accepted. That is the state in which
       founder-review minutes are being spent and the outcome is still unknown,
       so the metric could not detect the problem the ticket exists to measure.
    2. `linear_state_after` is a hardcoded literal — `"In Review" if (issue_id
       and push_ok) else ""`, set once at push time in session_linear.py and
       never revisited. It is the ONLY value ever written, so the five-element
       accepted-states set matched a constant.
    3. The Supabase path filtered `linear_state_after=not.is.null` while the
       write site sent `_linear_state or None`. Failed pushes therefore wrote
       NULL and were dropped from the denominator, while every surviving row
       said "In Review" and scored as accepted — so C2 returned 5/5 by
       construction whenever any row existed.

    It now reads `accepted_at` / `accepted_state_type`, written by
    supabase_log.record_acceptance() from the Linear terminal-transition
    webhook. Open issues are excluded from both numerator and denominator.
    """
    def _score_from_rows(rows: list[dict], source: str) -> tuple[int, str] | None:
        """Score C2 from rows carrying a TERMINAL outcome. None if no data.

        Denominator is issues that reached a terminal Linear state; numerator is
        those whose terminal state was an acceptance ("completed") rather than a
        rejection ("canceled"). Issues still open are excluded from BOTH — their
        outcome is genuinely unknown, and counting them either way is a guess.
        """
        total = accepted = 0
        for r in rows:
            if not r.get("accepted_at"):
                continue          # still open — outcome unknown, not a data point
            total += 1
            if (r.get("accepted_state_type") or "").lower() == "completed":
                accepted += 1
        if total == 0:
            return None
        rate = accepted / total
        # Sample floor. Without it a single accepted issue scores 1/1 = 100% and
        # lands the whole card in the top band — a routing decision driven by one
        # data point. RA-7216 requires rejecting metrics that cannot change a
        # decision correctly, and a 100% built from n=1 changes it wrongly.
        # 5 is a starting threshold, not a derived one; retune once the 30-day
        # baseline exists and the real weekly volume is known.
        if total < _C2_MIN_SAMPLE:
            return 1, (
                f"needs_data — only {total} terminal outcome(s) in window, below the "
                f"{_C2_MIN_SAMPLE}-sample floor; {accepted}/{total} accepted is "
                f"DIAGNOSTIC ONLY [{source}]"
            )
        note = f"{accepted}/{total} terminal outcomes accepted ({rate:.0%}) [{source}]"
        if rate >= 0.90:
            return 5, note
        if rate >= 0.75:
            return 4, note
        if rate >= 0.55:
            return 3, note
        if rate >= 0.30:
            return 2, note
        return 1, note

    # ── Supabase gate_checks — the only source with a terminal outcome ────────
    # No `not.is.null` filter on the acceptance columns: filtering at the query
    # is what produced the old survivorship bias, because the write site turned
    # a missing state into NULL and the read site then dropped exactly those
    # rows. The window is the only filter; _score_from_rows decides what counts.
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+", "%2B")
    sb_rows = _supabase_query(
        "gate_checks",
        "shipped,accepted_at,accepted_state_type,checked_at",
        f"checked_at=gte.{cutoff_iso}&order=checked_at.desc&limit=500",
    )
    result = _score_from_rows(sb_rows, "supabase")
    if result is not None:
        return result

    # No JSONL fallback. session-outcomes.jsonl is written at PUSH time by
    # _record_session_outcome(), so it cannot carry a terminal outcome — the
    # outcome arrives hours or days later via the Linear webhook. The old
    # fallback scored a different population from the Supabase path using a
    # different rule, which meant C2's meaning depended on which backend
    # answered. An honest needs_data beats a second definition.
    if not sb_rows:
        return 1, "needs_data — no gate_check rows in window (or Supabase unreachable)"
    return 1, (
        f"needs_data — {len(sb_rows)} rows in window but none has reached a terminal "
        f"Linear state yet; acceptance is unknown, not zero"
    )


def score_c3_mean_time_to_value(rows: list[dict]) -> tuple[int, str]:
    """C3: Median trigger-to-deploy time in minutes."""
    durations = []
    for r in rows:
        start = r.get("session_started_at")
        push = r.get("push_timestamp")
        if start and push and r.get("shipped"):
            try:
                t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(push.replace("Z", "+00:00"))
                durations.append((t1 - t0).total_seconds() / 60)
            except Exception:
                pass
    if not durations:
        return 1, "needs_data — no shipped sessions with push_timestamp yet (will populate once swarm starts building)"
    durations.sort()
    median = durations[len(durations) // 2]
    note = f"median {median:.0f} min over {len(durations)} builds"
    if median <= 20:
        return 5, note
    if median <= 40:
        return 4, note
    if median <= 90:
        return 3, note
    if median <= 180:
        return 2, note
    return 1, note


def score_c4_security_posture(projects: list[dict]) -> tuple[int, str]:
    """C4: Pi-SEO portfolio security posture."""
    if not projects:
        return 1, "no scan data available"
    sec_scores = [p["scores"].get("security", 0) for p in projects if "scores" in p]
    if not sec_scores:
        return 1, "no security scores"
    avg = sum(sec_scores) / len(sec_scores)
    # rollback tracking not wired — use score as proxy (criticals count pending RA-672)
    note = f"portfolio avg {avg:.0f}, {len(sec_scores)} repos scanned"
    if avg >= 80 and all(s >= 80 for s in sec_scores):
        return 5, note
    if avg >= 60:
        return 4, note
    if avg >= 40:
        return 3, note
    if avg >= 20:
        return 2, note
    return 1, note


def score_c5_knowledge_velocity(lpw: float, rows: list[dict]) -> tuple[int, str]:
    """C5: Lessons per week + evaluator trend."""
    scores = [r.get("review_score", 0) for r in rows if r.get("review_score")]
    eval_avg = sum(scores) / len(scores) if scores else None
    note_parts = [f"{lpw:.1f} lessons/week"]
    if eval_avg is not None:
        note_parts.append(f"eval avg {eval_avg:.1f}/10")
    note = ", ".join(note_parts)
    good_vel = lpw >= 5
    good_eval = eval_avg is not None and eval_avg >= 7.5
    if good_vel and good_eval:
        return 5, note
    if lpw >= 3 or (eval_avg is not None and eval_avg >= 7.0):
        return 4, note
    if lpw >= 1 or (eval_avg is not None and eval_avg >= 6.0):
        return 3, note
    if lpw > 0:
        return 2, note
    return 1, f"no lessons in window — {note}"


# ─── v1 components (loaded from leverage-audit.md) ───────────────────────────

def _load_v1_score() -> tuple[int, int]:
    """Read current v1 score from leverage-audit.md header."""
    audit = _HARNESS / "leverage-audit.md"
    if not audit.exists():
        return 60, 75  # assumed full Section A
    for line in audit.read_text(encoding="utf-8").splitlines():
        if "Current Score:" in line or "Grand Total:" in line:
            import re
            m = re.search(r"(\d+)\s*/\s*75", line)
            if m:
                v1 = int(m.group(1))
                return v1, 75
    return 73, 75  # known baseline


# ─── main ─────────────────────────────────────────────────────────────────────

def compute_v2_score(days: int = 30) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Load gate_checks for the window; fall back to local session-outcomes.jsonl
    # when Supabase credentials are absent (dev / Mac Mini environment).
    rows = _supabase_query(
        "gate_checks",
        "shipped,review_score,session_started_at,push_timestamp,checked_at,merge_sha,accepted_at,accepted_state_type",
        f"checked_at=gte.{cutoff}&order=checked_at.desc&limit=500",
    )
    if not rows:
        rows = _load_outcomes_as_gate_rows(days)

    projects = _load_scanner_summary()
    lpw = _lessons_per_week(days)

    c1_score, c1_note = score_c1_deployment_success(rows, days)
    c2_score, c2_note = score_c2_output_acceptance(days)
    c3_score, c3_note = score_c3_mean_time_to_value(rows)
    c4_score, c4_note = score_c4_security_posture(projects)
    c5_score, c5_note = score_c5_knowledge_velocity(lpw, rows)

    section_c = c1_score + c2_score + c3_score + c4_score + c5_score
    v1_score, _ = _load_v1_score()
    total = v1_score + section_c

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "gate_check_rows": len(rows),
        "v1_score": v1_score,
        "section_c": {
            "C1_deployment_success": {"score": c1_score, "max": 5, "note": c1_note},
            "C2_output_acceptance":  {"score": c2_score, "max": 5, "note": c2_note},
            "C3_mean_time_to_value": {"score": c3_score, "max": 5, "note": c3_note},
            "C4_security_posture":   {"score": c4_score, "max": 5, "note": c4_note},
            "C5_knowledge_velocity": {"score": c5_score, "max": 5, "note": c5_note},
            "total": section_c,
            "max":   25,
        },
        "ra7216_metrics": compute_ra7216_metrics(rows, days),
        "v2_total": total,
        "v2_max": 100,
        "band": _band(total),
    }

    # Persist for board meeting consumption
    _HARNESS.mkdir(exist_ok=True)
    _OUTPUT.write_text(json.dumps(result, indent=2))
    return result


def compute_ra7216_metrics(rows: list[dict], days: int = 30) -> dict:
    """The seven RA-7216 metrics: each a real value or an explicit needs_data.

    Separate from the ZTE Section C card because RA-7216 is a different
    contract: PR and token counts are diagnostic-only there, and no metric here
    may report a number it cannot support.

    Review latency is DERIVED (`accepted_at - push_timestamp`), not stored, per
    the founder's 14/08/2026 instrument decision — one source of truth, no
    column that can drift from its own inputs. It is named `review_latency` and
    not `review_minutes` on purpose: it measures how long the change sat in the
    queue, not how long a human attended to it. Conflating the two would
    overstate founder effort by every idle overnight hour.
    """
    def _dt(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    terminal = [r for r in rows if r.get("accepted_at")]
    accepted = [r for r in terminal
                if (r.get("accepted_state_type") or "").lower() == "completed"]
    reopens = _fetch_outcome_events("reopen", days)

    latencies, trigger_to_accepted = [], []
    for r in accepted:
        acc, push, start = _dt(r.get("accepted_at")), _dt(r.get("push_timestamp")), _dt(r.get("session_started_at"))
        if acc and push:
            latencies.append((acc - push).total_seconds() / 60)
        if acc and start:
            trigger_to_accepted.append((acc - start).total_seconds() / 60)

    def _median(xs):
        return sorted(xs)[len(xs) // 2] if xs else None

    def _needs(reason):
        return {"value": None, "state": "needs_data", "reason": reason}

    def _value(v, unit, provenance):
        return {"value": v, "state": "measured", "unit": unit, "provenance": provenance}

    return {
        "first_pass_acceptance": (
            _value(round(len(accepted) / len(terminal), 3), "ratio",
                   "gate_checks.accepted_state_type over terminal outcomes")
            if terminal else _needs("no terminal outcomes in window")
        ),
        "human_correction_count": _needs(
            "no source. Nothing attributes post-merge commits to a human author; "
            "measuring it needs a per-commit authorship feed that does not exist. "
            "Not inferred from reopen count — a reopen is not a correction."
        ),
        "rework_ratio": (
            _value(round(len(reopens) / len(accepted), 3), "ratio",
                   "outcome_events.reopen over accepted outcomes")
            if accepted else _needs("no accepted outcomes in window")
        ),
        "rollback_escaped_defects": _value(
            len(_fetch_outcome_events("revert", days)), "count",
            "outcome_events.revert — see C1 for rate, coverage and unattributed"
        ),
        "trigger_to_accepted_outcome": (
            _value(round(_median(trigger_to_accepted), 1), "minutes",
                   "median accepted_at - session_started_at")
            if trigger_to_accepted else _needs("no accepted row carries both timestamps yet")
        ),
        "review_latency": (
            _value(round(_median(latencies), 1), "minutes",
                   "median accepted_at - push_timestamp. QUEUE time, not attention time")
            if latencies else _needs("no accepted row carries both timestamps yet")
        ),
        "cost_per_accepted_outcome": _needs(
            "llm_costs covers only the provider_router path until the Agent SDK "
            "writer ships; a figure now would be biased far low"
        ),
    }


def _band(score: int) -> str:
    if score >= 95:
        return "Zero Touch Elite"
    if score >= 80:
        return "Zero Touch"
    if score >= 56:
        return "Autonomous"
    if score >= 34:
        return "Assisted"
    return "Manual"


def _print_card(r: dict) -> None:
    sc = r["section_c"]
    print(f"\n{'─'*55}")
    print(f"  ZTE Framework v2 Score  —  {r['computed_at'][:10]}")
    print(f"{'─'*55}")
    print(f"  v1 base (A+B):  {r['v1_score']:>3} / 75")
    print(f"  Section C:      {sc['total']:>3} / 25")
    print(f"  {'─'*30}")
    print(f"  TOTAL:          {r['v2_total']:>3} / 100  [{r['band']}]")
    print(f"\n  Section C breakdown ({r['window_days']}-day window, {r['gate_check_rows']} gate_check rows):")
    for key, dim in sc.items():
        if key in ("total", "max"):
            continue
        label = key.split("_", 1)[1].replace("_", " ").title()
        print(f"    {dim['score']}/5  {label}")
        print(f"         {dim['note']}")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute ZTE v2 score")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    args = parser.parse_args()

    result = compute_v2_score(days=args.days)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_card(result)
        print(f"  Written to {_OUTPUT}")
