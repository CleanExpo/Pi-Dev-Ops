#!/usr/bin/env python3
"""swarm_review.py — independent review panel over OpenRouter, citation-verified.

Replaces the single-Codex reviewer lane with a panel of independent models, most of
them free. Built after 2026-08-17, when Codex hit a usage limit and stalled a release
for hours while 413 OpenRouter models sat unused.

Why citation verification is not optional here
----------------------------------------------
Measured on the run that motivated this tool: given a diff whose only third-party-IP
issue was in `skills/carsi-course-production/evals/calibration/bad-04.md`,
`nvidia/nemotron-3.5-lightning:free` returned well-formed JSON and a confident P0
titled "Third-party IP reproduction risk in scripts/handoff-loop.sh npm cache probe".
That shell script contains no such text. The model attached a real concept to the
wrong file. A swarm that counted votes without anchoring citations would have scored
that as corroboration.

So every blocking finding is passed through verify_reviewer_citations.py, which
indexes the diff post-image and discards any finding whose `quoted_line` does not
appear under the file it names. Unanchored findings never reach the verdict.

Authorship
----------
Each finding stays byte-identical to what its authoring model emitted, and carries
`reviewer_agent`. This script only transports, filters mechanically, and counts —
it never rewrites a verdict or a finding. The pr-release-gate rule that the
implementing agent must not author the report is preserved: the models are the
authors, this is the courier.

Usage
-----
  swarm_review.py --diff DIFF --base SHA --head SHA --out DIR [--tier free|cheap|mixed]

Exit: 0 = PASS (no anchored P0/P1), 1 = FAIL (anchored blockers), 2 = panel unusable.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VERIFIER = pathlib.Path(__file__).with_name("verify_reviewer_citations.py")

TIERS_CONFIG = pathlib.Path(__file__).with_name("swarm_tiers.json")


def load_tiers(path: pathlib.Path = TIERS_CONFIG) -> dict[str, list[str]]:
    """Read the MEASURED tier definitions from swarm_tiers.json.

    Tiers are data, not code, because they are benchmark output: swarm_bench.py
    scored 142 models against real defects and the winners are recorded there. When
    the benchmark is re-run the config changes and this script needs no edit.

    There is deliberately NO hardcoded fallback. An earlier revision carried its
    tiers inline, the config was added later, and the two silently disagreed on all
    four tiers — `--tier mixed` kept running a guessed list containing two models the
    benchmark had since scored badly (x-ai/grok-4.6 at 2/4, and openrouter/free,
    which returned a schema template instead of a report). A fallback would have
    hidden exactly that drift, so a missing or malformed config is a hard error:
    running an unmeasured panel and calling it the measured one is the failure this
    file exists to prevent.
    """
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(
            f"swarm tier config missing: {path}\n"
            "Tiers are benchmark output, not defaults. Re-create it with swarm_bench.py, "
            "or pass --models explicitly."
        )
    except json.JSONDecodeError as e:
        raise SystemExit(f"swarm tier config is not valid JSON: {path}: {e}")

    tiers = raw.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise SystemExit(f"swarm tier config has no 'tiers' object: {path}")

    out: dict[str, list[str]] = {}
    for name, spec in tiers.items():
        models = [m.get("id") for m in (spec or {}).get("models", []) if m.get("id")]
        if not models:
            raise SystemExit(f"swarm tier '{name}' lists no models in {path}")
        out[name] = models
    return out


TIERS = load_tiers()

SYSTEM = """You are an INDEPENDENT RELEASE REVIEWER. REFUTE, do not bless. Default FAIL when uncertain.
Return ONE JSON object, nothing else, no markdown fence:
{"schema":2,"reviewer_agent":"<model>","base_sha":"...","head_sha":"...",
 "verdict":"PASS|FAIL",
 "blocking_findings":[{"severity":"P0|P1","title":"...","file":"...","line":0,
   "quoted_line":"<copied VERBATIM from a + or context line of the diff, under the file you name>",
   "reproduction":"...","suggested_fix":"..."}],
 "checklist":[{"id":"coverage-ledger","verdict":"PASS|N/A","evidence":"...","reason":"(if N/A)"}],
 "coverage":{"reviewed":["path"],"not_reviewed":[{"path":"p","reason":"r"}]}}

checklist ids, all eight required: coverage-ledger, plan-conformance, weakened-checks,
mutation-control, guard-falsification, clean-environment-suite, blast-radius, outbound-actions.

You cannot execute commands. Mark execution-dependent items N/A with that reason — never PASS.
A quoted_line that is not in the diff under that file is discarded automatically, so never
invent one. If you cannot cite it, do not file it. P2 observations go outside blocking_findings.
coverage.reviewed + coverage.not_reviewed must account for every supplied changed file."""


def call_model(model: str, system: str, user: str, key: str, timeout: int) -> dict:
    """One model, one review. Never raises — failures come back as a status dict."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        # 12000 truncated a real report mid-object on nemotron-3.5-lightning (2026-08-17),
        # which then failed json.loads and was scored "unparseable" — a capability
        # miss caused entirely by our own cap.
        "max_tokens": 32000,
        # Ask for a JSON object where the provider supports it. Reasoning models
        # otherwise return chain-of-thought in `reasoning` with `content` empty;
        # openrouter/free returned 43KB of thinking and no report that way.
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        # Keep the body. "400 Bad Request" alone is undiagnosable, and the body
        # usually names the unsupported parameter.
        try:
            detail = f"{e.code} {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception:
            detail = f"{e.code} {e.reason}"
        return {"model": model, "status": "http_error", "detail": detail}
    except Exception as e:  # transport, timeout, decode
        return {"model": model, "status": "transport_error", "detail": type(e).__name__}

    if "choices" not in resp:
        detail = (resp.get("error") or {}).get("message", "no choices")
        return {"model": model, "status": "api_error", "detail": str(detail)[:200]}

    choice = resp["choices"][0]
    msg = choice.get("message", {})
    # Reasoning models sometimes put the payload in `reasoning` and leave content null.
    text = msg.get("content") or msg.get("reasoning") or ""
    finish = choice.get("finish_reason")
    usage = resp.get("usage", {})
    return {
        "model": model,
        "status": "ok",
        "text": text,
        "elapsed_s": round(time.time() - t0),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "finish_reason": finish,
    }


def _is_real_report(obj: dict) -> bool:
    """Reject the schema template echoed back as if it were a review.

    Reasoning models quote the requested schema verbatim inside their thinking.
    Those echoes carry every report-shaped key, so key-count scoring ranks them
    above genuine reports — openrouter/free scored a template with
    verdict "PASS|FAIL" and severity "P0|P1" over a real one (2026-08-17).
    A real verdict is exactly PASS or FAIL; a placeholder never is.
    """
    if obj.get("verdict") not in ("PASS", "FAIL"):
        return False
    for finding in obj.get("blocking_findings") or []:
        if str(finding.get("severity")) not in ("P0", "P1"):
            return False
    return True


def extract_json(text: str) -> dict | None:
    """Pull a schema-2 report out of a model response.

    Handles three shapes seen in the wild (measured 2026-08-17):
      1. clean JSON object;
      2. JSON embedded in prose or a markdown fence;
      3. a report buried at the end of chain-of-thought, because the model wrote to
         `reasoning` with `content` empty.
    Scans every balanced `{...}` span and scores the ones that parse, keeping the
    RICHEST report rather than the first or last.

    "Last" and "first" were both tried and both wrong (2026-08-17): a reasoning dump
    quotes schema fragments before and after the real report, so `first` caught a
    prose preamble and `last` caught a trailing `{"verdict":"PASS|N/A"}` example —
    scoring a genuine FAIL-with-P0 as a clean PASS. Selecting the wrong object here
    silently flips a verdict, so the selector must be positive about what a report
    looks like: report-shaped keys present, and more of them beats fewer.
    """
    if not text:
        return None

    MARKERS = ("schema", "base_sha", "head_sha", "checklist", "coverage",
               "blocking_findings", "reviewer_agent")
    best: dict | None = None
    best_score = -1
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    for start in starts:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict) and _is_real_report(obj):
                        score = sum(1 for m in MARKERS if m in obj)
                        # A bare {"verdict": ...} fragment scores 0 and can never
                        # displace a real report.
                        if score > best_score:
                            best, best_score = obj, score
                    break
    return best if best_score > 0 else None


def anchored_findings(report: dict, diff_path: str, workdir: pathlib.Path) -> list[dict]:
    """Return only the blocking findings the citation verifier accepts.

    Delegates to verify_reviewer_citations.py rather than reimplementing diff
    indexing — that script already handles octal-escaped UTF-8 and post-image-only
    indexing, and it is the same instrument the release gate trusts.
    """
    findings = report.get("blocking_findings") or []
    if not findings:
        return []

    kept: list[dict] = []
    for idx, finding in enumerate(findings):
        probe = workdir / f"probe-{idx}.json"
        probe.write_text(json.dumps({**report, "blocking_findings": [finding]}))
        result = subprocess.run(
            [sys.executable, str(VERIFIER), str(probe), diff_path],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            kept.append(finding)
    return kept


def finding_key(finding: dict) -> tuple[str, str]:
    """Dedup key: same file + same quoted line is the same defect."""
    return (
        str(finding.get("file", "")).strip(),
        re.sub(r"\s+", " ", str(finding.get("quoted_line", ""))).strip()[:120],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", required=True)
    ap.add_argument("--files", help="changed-file list; defaults to names parsed from diff")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tier", default="mixed", choices=sorted(TIERS))
    ap.add_argument("--models", help="comma-separated override of the tier list")
    ap.add_argument("--focus", default="", help="extra attack instructions for this diff")
    ap.add_argument("--timeout", type=int, default=1500)
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    diff = pathlib.Path(args.diff).read_text(encoding="utf-8", errors="replace")
    if args.files:
        files = pathlib.Path(args.files).read_text()
    else:
        files = "\n".join(sorted({m for m in re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)}))

    models = (
        [m.strip() for m in args.models.split(",") if m.strip()]
        if args.models
        else TIERS[args.tier]
    )
    user = (
        f"base_sha {args.base}\nhead_sha {args.head}\n\n"
        f"{args.focus}\n\nCHANGED FILES:\n{files}\n\nUNIFIED DIFF:\n{diff}"
    )

    print(f"swarm: {len(models)} reviewers, tier={args.tier}")
    results = []
    with cf.ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(call_model, m, SYSTEM, user, key, args.timeout): m for m in models
        }
        for fut in cf.as_completed(futures):
            results.append(fut.result())

    reports, panel = [], []
    for res in results:
        model = res["model"]
        slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
        if res["status"] != "ok":
            print(f"  {model:44} {res['status'].upper()}: {res.get('detail','')[:60]}")
            panel.append({"model": model, "status": res["status"], "detail": res.get("detail")})
            continue

        (out / f"{slug}.raw").write_text(res["text"])
        report = extract_json(res["text"])
        if report is None:
            print(f"  {model:44} UNPARSEABLE (kept at {slug}.raw)")
            panel.append({"model": model, "status": "unparseable"})
            continue

        report.setdefault("reviewer_agent", model)
        raw_n = len(report.get("blocking_findings") or [])
        kept = anchored_findings(report, args.diff, out)
        for finding in kept:
            finding["reviewer_agent"] = model
        rejected = raw_n - len(kept)
        print(
            f"  {model:44} {report.get('verdict','?'):4} "
            f"findings={raw_n} anchored={len(kept)} rejected={rejected} "
            f"in={res['prompt_tokens']} {res['elapsed_s']}s"
        )
        panel.append(
            {
                "model": model,
                "status": "ok",
                "verdict": report.get("verdict"),
                "findings_raw": raw_n,
                "findings_anchored": len(kept),
                "findings_rejected_unanchored": rejected,
                "prompt_tokens": res["prompt_tokens"],
                "elapsed_s": res["elapsed_s"],
                "coverage_reviewed": len((report.get("coverage") or {}).get("reviewed", [])),
            }
        )
        reports.append((report, kept))

    usable = [r for r in reports]
    if not usable:
        print("\nPANEL UNUSABLE — no model returned a parseable report")
        return 2

    # Merge anchored findings, counting corroboration. Verbatim, never rewritten.
    merged: dict[tuple[str, str], dict] = {}
    for _report, kept in usable:
        for finding in kept:
            k = finding_key(finding)
            if k in merged:
                merged[k].setdefault("corroborated_by", []).append(finding["reviewer_agent"])
            else:
                entry = dict(finding)
                entry["corroborated_by"] = [finding["reviewer_agent"]]
                merged[k] = entry

    blocking = sorted(
        merged.values(),
        key=lambda f: (str(f.get("severity", "P1")), -len(f.get("corroborated_by", []))),
    )
    verdict = "FAIL" if blocking else "PASS"

    # Checklist: worst answer wins across the panel. A single N/A means the panel as a
    # whole did not discharge that item, which is the honest reading.
    checklist: dict[str, dict] = {}
    for report, _ in usable:
        for item in report.get("checklist") or []:
            cid = item.get("id")
            if not cid:
                continue
            if cid not in checklist or checklist[cid].get("verdict") == "PASS":
                checklist[cid] = item

    consensus = {
        "schema": 2,
        "implementation_agent": "claude",
        "reviewer_agent": "openrouter-swarm(" + ",".join(p["model"] for p in panel) + ")",
        "reviewer_session_id": f"swarm-{args.head[:12]}",
        "base_sha": args.base,
        "head_sha": args.head,
        "verdict": verdict,
        "blocking_findings": blocking,
        "checklist": list(checklist.values()),
        "coverage": {
            "reviewed": sorted(
                {
                    p
                    for report, _ in usable
                    for p in (report.get("coverage") or {}).get("reviewed", [])
                }
            ),
            "not_reviewed": [],
        },
        "panel": panel,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # Any changed file no reviewer listed is declared unreviewed rather than assumed clean.
    seen = set(consensus["coverage"]["reviewed"])
    consensus["coverage"]["not_reviewed"] = [
        {"path": f, "reason": "no panel member listed this file as reviewed"}
        for f in files.split()
        if f and f not in seen
    ]

    dest = out / "reviewer-report.json"
    dest.write_text(json.dumps(consensus, indent=2))
    print(f"\nVERDICT: {verdict}  anchored_blockers={len(blocking)}")
    for finding in blocking:
        agents = ",".join(finding.get("corroborated_by", []))
        print(f"  [{finding.get('severity')}] {finding.get('file')} — {finding.get('title')}")
        print(f"      corroborated_by: {agents}")
    print(f"report: {dest}")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
