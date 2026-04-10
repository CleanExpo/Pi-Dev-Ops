#!/usr/bin/env python3
"""marathon_pi_seo_dryrun.py — hourly Pi-SEO dry-run digest writer.

Aggregates .harness/scan-results/{repo}/*.json files into a new dated digest
under .harness/monitor-digests/. Pushes a Telegram ALERT if a NEW critical
finding appeared since the previous digest.

No LLM tools required. Runs as a single python3 invocation.

Exit codes:
  0 — digest written
  1 — no scan results present
  2 — write error
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIR = REPO_ROOT / ".harness" / "scan-results"
DIGEST_DIR = REPO_ROOT / ".harness" / "monitor-digests"
SEND_SCRIPT = REPO_ROOT / "scripts" / "send_telegram.py"

SEVERITY_THRESHOLD = {"critical", "high"}  # founder decision 2026-04-11


def _load_repo_findings(repo_dir: Path) -> dict[str, list]:
    """Return {category: [findings]} for a repo, filtered to critical+high."""
    out: dict[str, list] = {}
    for path in sorted(repo_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        category = path.stem.split("-", maxsplit=3)[-1]  # 2026-04-10-security -> security
        findings = data.get("findings", []) if isinstance(data, dict) else []
        keep = [
            f for f in findings
            if isinstance(f, dict)
            and str(f.get("severity", "")).lower() in SEVERITY_THRESHOLD
        ]
        if keep:
            out.setdefault(category, []).extend(keep)
    return out


def _score_repo(findings_by_cat: dict[str, list]) -> int:
    """Simple heuristic: 100 minus 10/critical minus 3/high, floor 0."""
    score = 100
    for findings in findings_by_cat.values():
        for f in findings:
            sev = str(f.get("severity", "")).lower()
            if sev == "critical":
                score -= 10
            elif sev == "high":
                score -= 3
    return max(0, score)


def _finding_fingerprint(f: dict) -> str:
    """Stable key for diff detection."""
    return f"{f.get('file', '')}:{f.get('line', '')}:{f.get('severity', '')}:{f.get('message', '')[:60]}"


def _previous_critical_set() -> set[str]:
    """Return fingerprints of critical findings from the most recent prior digest."""
    if not DIGEST_DIR.exists():
        return set()
    files = sorted(DIGEST_DIR.glob("dryrun-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return set()
    # Parse fingerprints from the most recent digest's machine-readable block
    try:
        text = files[0].read_text(encoding="utf-8")
        marker = "CRITICAL_FINGERPRINTS:"
        if marker not in text:
            return set()
        block = text.split(marker, 1)[1].strip().splitlines()
        return {line.strip() for line in block if line.strip() and not line.startswith("---")}
    except Exception:
        return set()


def main() -> int:
    if not SCAN_DIR.exists():
        print(f"no scan dir at {SCAN_DIR}", file=sys.stderr)
        return 1

    repo_dirs = sorted([p for p in SCAN_DIR.iterdir() if p.is_dir()])
    if not repo_dirs:
        print("no repo scan folders", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d-%H%M")

    rows = []
    total_critical = 0
    total_high = 0
    current_fingerprints: set[str] = set()

    for repo_dir in repo_dirs:
        findings_by_cat = _load_repo_findings(repo_dir)
        critical = [f for findings in findings_by_cat.values() for f in findings
                    if str(f.get("severity", "")).lower() == "critical"]
        high = [f for findings in findings_by_cat.values() for f in findings
                if str(f.get("severity", "")).lower() == "high"]
        score = _score_repo(findings_by_cat)
        total_critical += len(critical)
        total_high += len(high)
        for f in critical:
            current_fingerprints.add(_finding_fingerprint(f))
        rows.append({
            "repo": repo_dir.name,
            "score": score,
            "critical": len(critical),
            "high": len(high),
            "categories": sorted(findings_by_cat.keys()),
        })

    # Portfolio health = average score
    if rows:
        portfolio_health = sum(r["score"] for r in rows) // len(rows)
    else:
        portfolio_health = 0

    # Write digest
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DIGEST_DIR / f"dryrun-{timestamp}.md"

    lines = [
        f"# Pi-SEO Dry-Run Digest — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Portfolio health:** {portfolio_health}/100",
        f"**Repos scanned:** {len(rows)}",
        f"**Critical findings:** {total_critical}",
        f"**High findings:** {total_high}",
        f"**Severity threshold:** critical + high (founder decision 2026-04-11)",
        "",
        "## Per-repo breakdown",
        "",
        "| Repo | Score | Critical | High | Categories |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: x["score"]):
        cats = ", ".join(r["categories"]) if r["categories"] else "—"
        lines.append(f"| {r['repo']} | {r['score']}/100 | {r['critical']} | {r['high']} | {cats} |")

    lines += [
        "",
        "## Machine-readable fingerprints",
        "",
        "CRITICAL_FINGERPRINTS:",
    ]
    lines.extend(sorted(current_fingerprints))

    try:
        out_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        print(f"write failed: {e}", file=sys.stderr)
        return 2

    # Diff against previous
    previous = _previous_critical_set()
    new_criticals = current_fingerprints - previous
    if new_criticals and SEND_SCRIPT.exists():
        msg_lines = [f"PI-SEO ALERT: {len(new_criticals)} NEW critical finding(s)"]
        for fp in sorted(new_criticals)[:5]:
            msg_lines.append(f"- {fp}")
        if len(new_criticals) > 5:
            msg_lines.append(f"- ... and {len(new_criticals) - 5} more")
        msg_lines.append(f"Digest: {out_path.name}")
        try:
            subprocess.run(
                ["python3", str(SEND_SCRIPT), "\n".join(msg_lines)],
                timeout=30,
            )
        except Exception as e:
            print(f"telegram push failed: {e}", file=sys.stderr)

    print(f"digest written: {out_path}")
    print(f"new critical findings: {len(new_criticals)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
