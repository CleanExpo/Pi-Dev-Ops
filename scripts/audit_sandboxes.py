#!/usr/bin/env python3
"""
audit_sandboxes.py — assert framework != null on every *-sandbox Vercel project.

Purpose
-------
RA-5262 / RA-5697: Vercel "sandbox" projects across the Unite-Group team keep
silently drifting into `framework: null`. When a project loses its framework
preset, Vercel can no longer infer the build/output settings, so preview
deployments for that project fail — and because the failing check is a required
gate, it wedges every open PR with a permanent red check until an agent stops
admin-merging and finally investigates.

This auditor walks the team's Vercel projects, filters to the ones whose name
ends in `-sandbox`, and flags any that either:

  1. have `framework == null` (the drift itself), or
  2. have no READY deployment in the last 7 days (a stale sandbox that is no
     longer serving previews — the downstream symptom of the same rot).

A Telegram alert fires when any drift is found (best-effort, same helper as the
DNS takeover scanner).

Design choices
--------------
* Zero third-party deps — uses `urllib`/`json` from stdlib.
* Self-contained — no FastAPI, no MCP. Suitable for a GitHub Action / cron.
* All findings print as JSON lines to stdout so downstream tooling (jq, the GH
  step summary, Linear auto-ticket) can parse cleanly.

Env
---
    VERCEL_TOKEN            — required; personal/team token with read scope.
    VERCEL_TEAM_ID          — team slug id (default team_KMZACI5rIltoCRhAtGCXlxUf).
    SANDBOX_AUDIT_TELEGRAM  — "1" (default) sends a Telegram alert on drift; "0" mutes.
    SANDBOX_MAX_AGE_DAYS    — READY-deployment freshness window (default 7).

Exit codes
----------
    0 — audit ran, no drift
    1 — audit ran, at least one sandbox drifted
    2 — auditor failed (missing token, Vercel API error, etc.)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TEAM_ID = "team_KMZACI5rIltoCRhAtGCXlxUf"
VERCEL_API = "https://api.vercel.com"
SANDBOX_SUFFIX = "-sandbox"
_TIMEOUT_S = 20.0


@dataclass
class Finding:
    project: str
    project_id: str
    severity: str  # warn | critical
    kind: str      # framework-null | no-recent-ready-deploy
    detail: str
    framework: Optional[str] = None
    last_ready_deploy_age_days: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Vercel REST helpers — stdlib only
# ─────────────────────────────────────────────────────────────────────────────
def _get(path: str, token: str) -> dict[str, Any]:
    """GET a Vercel API path and return the decoded JSON object.

    Raises RuntimeError on any HTTP/transport/JSON error so the caller can
    convert it into an exit-code-2 auditor failure."""
    req = urllib.request.Request(
        f"{VERCEL_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = (exc.read().decode("utf-8", "replace") or "")[:300]
        raise RuntimeError(f"Vercel API {exc.code} for {path}: {body}") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Vercel API call failed for {path}: {exc}") from exc


def list_sandbox_projects(token: str, team_id: str) -> list[dict[str, Any]]:
    """Return all team projects whose name ends in `-sandbox`, paginating."""
    projects: list[dict[str, Any]] = []
    until: Optional[int] = None
    while True:
        path = f"/v9/projects?teamId={team_id}&limit=100"
        if until is not None:
            path += f"&until={until}"
        data = _get(path, token)
        for p in data.get("projects", []):
            if str(p.get("name", "")).endswith(SANDBOX_SUFFIX):
                projects.append(p)
        pagination = data.get("pagination") or {}
        until = pagination.get("next")
        if not until:
            break
    return projects


def _latest_ready_ts_ms(project: dict[str, Any]) -> Optional[int]:
    """Return the createdAt (ms) of the most recent READY deployment, or None.

    Reads the `latestDeployments` array the /v9/projects response embeds — each
    entry carries `readyState`/`state` plus a `createdAt` epoch-ms. Avoids an
    N+1 call to /v6/deployments for the common case where a sandbox has recent
    activity."""
    best: Optional[int] = None
    for dep in project.get("latestDeployments") or []:
        state = str(dep.get("readyState") or dep.get("state") or "").upper()
        if state != "READY":
            continue
        ts = dep.get("createdAt") or dep.get("created")
        if isinstance(ts, (int, float)):
            ts = int(ts)
            if best is None or ts > best:
                best = ts
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Auditor core
# ─────────────────────────────────────────────────────────────────────────────
def audit(token: str, team_id: str, max_age_days: float) -> list[Finding]:
    findings: list[Finding] = []
    now_ms = int(time.time() * 1000)
    max_age_ms = max_age_days * 24 * 60 * 60 * 1000

    for project in list_sandbox_projects(token, team_id):
        name = str(project.get("name", "<unknown>"))
        pid = str(project.get("id", ""))
        framework = project.get("framework")

        if framework is None:
            findings.append(Finding(
                project=name,
                project_id=pid,
                severity="critical",
                kind="framework-null",
                detail="framework is null — Vercel cannot infer build/output "
                       "settings, so preview deployments fail and wedge every "
                       "open PR behind a permanent red required check. Set the "
                       "framework preset in Project Settings → Build & Development.",
                framework=None,
            ))
            # framework-null is the root drift; still report deploy staleness
            # below so the summary is complete.

        ready_ms = _latest_ready_ts_ms(project)
        if ready_ms is None:
            findings.append(Finding(
                project=name,
                project_id=pid,
                severity="warn",
                kind="no-recent-ready-deploy",
                detail="no READY deployment found in the embedded deployment "
                       "history — the sandbox is not serving previews.",
                framework=framework if isinstance(framework, str) else None,
                last_ready_deploy_age_days=None,
            ))
        else:
            age_ms = now_ms - ready_ms
            if age_ms > max_age_ms:
                findings.append(Finding(
                    project=name,
                    project_id=pid,
                    severity="warn",
                    kind="no-recent-ready-deploy",
                    detail=f"most recent READY deployment is "
                           f"{age_ms / 86_400_000:.1f} days old (> {max_age_days:g}d "
                           f"window) — the sandbox may be stale.",
                    framework=framework if isinstance(framework, str) else None,
                    last_ready_deploy_age_days=round(age_ms / 86_400_000, 1),
                ))

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Output + Telegram alert
# ─────────────────────────────────────────────────────────────────────────────
def format_alert(findings: Iterable[Finding]) -> str:
    lines = ["🚨 Sandbox framework drift — findings:"]
    for f in findings:
        icon = "🔴" if f.severity == "critical" else "🟠"
        lines.append(f"{icon} {f.project} [{f.kind}]")
        lines.append(f"   {f.detail}")
    return "\n".join(lines)


def send_telegram_alert(text: str) -> None:
    """Best-effort Telegram push — swallow any failure so the auditor still
    exits cleanly with the finding count as its signal."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from send_telegram import send_telegram  # noqa: PLC0415
        send_telegram(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Telegram alert failed: {exc}", file=sys.stderr)


def main() -> int:
    token = (os.environ.get("VERCEL_TOKEN") or "").strip()
    if not token:
        print("[error] VERCEL_TOKEN not set — cannot query Vercel API", file=sys.stderr)
        return 2

    team_id = (os.environ.get("VERCEL_TEAM_ID") or DEFAULT_TEAM_ID).strip()
    try:
        max_age_days = float(os.environ.get("SANDBOX_MAX_AGE_DAYS", "7"))
    except ValueError:
        max_age_days = 7.0

    try:
        findings = audit(token, team_id, max_age_days)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    for f in findings:
        print(json.dumps(asdict(f)))

    if findings:
        if os.environ.get("SANDBOX_AUDIT_TELEGRAM", "1") == "1":
            send_telegram_alert(format_alert(findings))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
