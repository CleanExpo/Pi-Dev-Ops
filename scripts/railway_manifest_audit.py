#!/usr/bin/env python3
"""Audit Railway's live deployment manifest against Pi-CEO's deploy contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED = {
    "build.builder": "DOCKERFILE",
    "deploy.startCommand": "uvicorn app.server.main:app --host 0.0.0.0 --port 8080 --workers 1",
    "deploy.healthcheckPath": "/health",
    "deploy.healthcheckTimeout": 30,
}
EXPECTED_OPTIONS = {
    "build.dockerfilePath": {"Dockerfile", "/Dockerfile"},
}
EXPECTED_CONFIG_FILES = {"/railway.toml", "/railway.json"}


def _run_status() -> dict[str, Any]:
    proc = subprocess.run(
        ["railway", "status", "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "railway status failed").strip())
    return json.loads(proc.stdout)


def _get_path(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _iter_deployments(status: dict[str, Any]) -> list[dict[str, Any]]:
    deployments: list[dict[str, Any]] = []
    for env_edge in ((status.get("environments") or {}).get("edges") or []):
        env = env_edge.get("node") or {}
        for svc_edge in ((env.get("serviceInstances") or {}).get("edges") or []):
            svc = svc_edge.get("node") or {}
            latest = svc.get("latestDeployment") or {}
            if latest:
                deployments.append({
                    "environment": env.get("name"),
                    "service": svc.get("serviceName"),
                    "deployment_id": latest.get("id"),
                    "status": latest.get("status"),
                    "manifest": (latest.get("meta") or {}).get("serviceManifest") or {},
                    "config_file": (latest.get("meta") or {}).get("configFile"),
                    "commit": (latest.get("meta") or {}).get("commitHash"),
                })
    return deployments


def audit(status: dict[str, Any], environment: str | None = None, service: str | None = None) -> dict[str, Any]:
    deployments = _iter_deployments(status)
    if environment:
        deployments = [d for d in deployments if d["environment"] == environment]
    if service:
        deployments = [d for d in deployments if d["service"] == service]

    results = []
    for deployment in deployments:
        manifest = deployment["manifest"]
        mismatches = []
        if deployment["config_file"] not in EXPECTED_CONFIG_FILES:
            mismatches.append({
                "path": "configFile",
                "expected": sorted(EXPECTED_CONFIG_FILES),
                "actual": deployment["config_file"],
            })
        for path, expected in EXPECTED.items():
            actual = _get_path(manifest, path)
            if actual != expected:
                mismatches.append({"path": path, "expected": expected, "actual": actual})
        for path, expected in EXPECTED_OPTIONS.items():
            actual = _get_path(manifest, path)
            if actual not in expected:
                mismatches.append({"path": path, "expected": sorted(expected), "actual": actual})
        results.append({**deployment, "ok": not mismatches, "mismatches": mismatches})

    return {
        "ok": bool(results) and all(item["ok"] for item in results),
        "checked": len(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-json", type=Path, help="Read saved `railway status --json` output instead of calling Railway.")
    parser.add_argument("--environment", help="Limit to one Railway environment name.")
    parser.add_argument("--service", help="Limit to one Railway service name.")
    args = parser.parse_args(argv)

    try:
        status = json.loads(args.status_json.read_text(encoding="utf-8")) if args.status_json else _run_status()
        report = audit(status, environment=args.environment, service=args.service)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
