"""
probe_dr_nrpg_stripe_keys.py — Hourly Stripe-key watch for CleanExpo/DR-NRPG.

Probes the live DR-NRPG deployment using the checks documented in
CleanExpo/DR-NRPG STRIPE-SETUP-FOR-RANA.md section 7:

  - GET  /api/health          → stripe subsystem (balance.retrieve)
  - POST /api/store/checkout  → 503 = STRIPE_SECRET_KEY missing; 400 = key present
  - POST /api/stripe/webhook  → 500 missing secret; 400 missing signature = secret present

Usage:
    python scripts/probe_dr_nrpg_stripe_keys.py
    python scripts/probe_dr_nrpg_stripe_keys.py --url https://dr-nrpg-platform.vercel.app
    python scripts/probe_dr_nrpg_stripe_keys.py --json

Exit codes:
    0 — egress ok; STRIPE_SECRET_KEY healthy; webhook secret present
    1 — infrastructure failure (egress blocked, DNS, timeout, unreadable response)
    2 — egress ok; STRIPE_SECRET_KEY missing or unhealthy
    3 — STRIPE_SECRET_KEY ok; STRIPE_WEBHOOK_SECRET missing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_URL = "https://dr-nrpg-platform.vercel.app"
HEALTH_PATH = "/api/health"
CHECKOUT_PATH = "/api/store/checkout"
WEBHOOK_PATH = "/api/stripe/webhook"
TIMEOUT_S = 30


@dataclass
class ProbeResult:
    ok: bool
    exit_code: int
    egress_reachable: bool
    stripe_secret_configured: bool | None
    stripe_healthy: bool | None
    stripe_reason: str | None
    stripe_key_mode: str | None
    webhook_secret_configured: bool | None
    checkout_http_status: int | None
    webhook_http_status: int | None
    http_status: int | None
    url: str
    detail: str


def _http_json(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    timeout_s: int = TIMEOUT_S,
) -> tuple[int, dict[str, Any] | None, str]:
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw), raw
            except json.JSONDecodeError:
                return resp.status, None, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        return exc.code, payload, raw


def _fetch_health(base_url: str, timeout_s: int = TIMEOUT_S) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{HEALTH_PATH}"
    status, payload, _raw = _http_json(url, timeout_s=timeout_s)
    if status not in (200, 503) or not isinstance(payload, dict):
        raise urllib.error.HTTPError(url, status, "unexpected health response", {}, None)
    return status, payload


def _probe_checkout(base_url: str, timeout_s: int = TIMEOUT_S) -> tuple[int, bool | None]:
    """503 + payment-not-configured → secret missing; 400 invalid JSON → secret present."""
    url = f"{base_url.rstrip('/')}{CHECKOUT_PATH}"
    status, payload, raw = _http_json(url, method="POST", body=b"", timeout_s=timeout_s)
    if status == 503:
        return status, False
    if status == 400:
        return status, True
    text = json.dumps(payload) if payload is not None else raw
    if "not configured" in text.lower() or "payment processing" in text.lower():
        return status, False
    return status, None


def _probe_webhook(base_url: str, timeout_s: int = TIMEOUT_S) -> tuple[int, bool | None]:
    """500 missing STRIPE_WEBHOOK_SECRET → absent; 400 missing signature → present."""
    url = f"{base_url.rstrip('/')}{WEBHOOK_PATH}"
    status, payload, raw = _http_json(url, method="POST", body=b"{}", timeout_s=timeout_s)
    text = json.dumps(payload) if payload is not None else raw
    lower = text.lower()
    if status == 500 and "webhook_secret" in lower:
        return status, False
    if status == 400 and "signature" in lower:
        return status, True
    if "missing stripe_webhook_secret" in lower or "webhook secret" in lower and status >= 500:
        return status, False
    return status, None


def _classify_egress_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 403:
            return (
                "egress_policy_denied: HTTP 403 from proxy or edge — "
                "add dr-nrpg-platform.vercel.app to the Cloud Agent environment allowlist"
            )
        return f"http_error_{exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", exc)
        return f"url_error:{reason}"
    return type(exc).__name__


def probe(base_url: str = DEFAULT_URL, *, timeout_s: int = TIMEOUT_S) -> ProbeResult:
    health_url = f"{base_url.rstrip('/')}{HEALTH_PATH}"
    try:
        http_status, payload = _fetch_health(base_url, timeout_s=timeout_s)
        checkout_status, checkout_key_present = _probe_checkout(base_url, timeout_s=timeout_s)
        webhook_status, webhook_present = _probe_webhook(base_url, timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            ok=False,
            exit_code=1,
            egress_reachable=False,
            stripe_secret_configured=None,
            stripe_healthy=None,
            stripe_reason=None,
            stripe_key_mode=None,
            webhook_secret_configured=None,
            checkout_http_status=None,
            webhook_http_status=None,
            http_status=None,
            url=health_url,
            detail=_classify_egress_error(exc),
        )

    checks = payload.get("checks") if isinstance(payload, dict) else None
    stripe = checks.get("stripe") if isinstance(checks, dict) else None
    if not isinstance(stripe, dict):
        return ProbeResult(
            ok=False,
            exit_code=1,
            egress_reachable=True,
            stripe_secret_configured=None,
            stripe_healthy=None,
            stripe_reason="missing_stripe_check",
            stripe_key_mode=None,
            webhook_secret_configured=webhook_present,
            checkout_http_status=checkout_status,
            webhook_http_status=webhook_status,
            http_status=http_status,
            url=health_url,
            detail="health JSON missing checks.stripe",
        )

    stripe_status = str(stripe.get("status", ""))
    stripe_reason = stripe.get("reason")
    stripe_key_mode = stripe.get("keyMode") if isinstance(stripe.get("keyMode"), str) else None

    health_configured = stripe_reason != "not_configured"
    health_healthy = stripe_status == "healthy"

    # Prefer live route probes when they give a definitive signal.
    secret_configured = checkout_key_present if checkout_key_present is not None else health_configured
    stripe_healthy = health_healthy if checkout_key_present is None else checkout_key_present
    webhook_configured = webhook_present

    if not secret_configured or not stripe_healthy:
        reason = stripe_reason or stripe_status or f"checkout_http_{checkout_status}"
        return ProbeResult(
            ok=False,
            exit_code=2,
            egress_reachable=True,
            stripe_secret_configured=secret_configured,
            stripe_healthy=stripe_healthy,
            stripe_reason=str(reason) if reason else None,
            stripe_key_mode=stripe_key_mode,
            webhook_secret_configured=webhook_configured,
            checkout_http_status=checkout_status,
            webhook_http_status=webhook_status,
            http_status=http_status,
            url=health_url,
            detail=f"STRIPE_SECRET_KEY not configured (checkout={checkout_status}, health={stripe_reason})",
        )

    if webhook_configured is False:
        return ProbeResult(
            ok=False,
            exit_code=3,
            egress_reachable=True,
            stripe_secret_configured=True,
            stripe_healthy=True,
            stripe_reason=None,
            stripe_key_mode=stripe_key_mode,
            webhook_secret_configured=False,
            checkout_http_status=checkout_status,
            webhook_http_status=webhook_status,
            http_status=http_status,
            url=health_url,
            detail=f"STRIPE_WEBHOOK_SECRET missing (webhook HTTP {webhook_status})",
        )

    all_green = secret_configured and stripe_healthy and webhook_configured is not False
    return ProbeResult(
        ok=all_green,
        exit_code=0 if all_green else 2,
        egress_reachable=True,
        stripe_secret_configured=secret_configured,
        stripe_healthy=stripe_healthy,
        stripe_reason=None,
        stripe_key_mode=stripe_key_mode,
        webhook_secret_configured=webhook_configured,
        checkout_http_status=checkout_status,
        webhook_http_status=webhook_status,
        http_status=http_status,
        url=health_url,
        detail=(
            "STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET configured"
            if all_green
            else "partial configuration — see checkout/webhook status fields"
        ),
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Probe DR-NRPG Stripe key configuration")
    parser.add_argument("--url", default=os.environ.get("DR_NRPG_BASE_URL", DEFAULT_URL))
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_S)
    args = parser.parse_args(argv)

    result = probe(args.url, timeout_s=args.timeout)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        icon = "✅" if result.ok else "❌"
        print(f"{icon} DR-NRPG Stripe probe — exit {result.exit_code}")
        print(f"   url: {result.url}")
        print(f"   egress_reachable: {result.egress_reachable}")
        print(f"   stripe_secret_configured: {result.stripe_secret_configured}")
        print(f"   stripe_healthy: {result.stripe_healthy}")
        if result.stripe_reason:
            print(f"   stripe_reason: {result.stripe_reason}")
        if result.stripe_key_mode:
            print(f"   stripe_key_mode: {result.stripe_key_mode}")
        print(f"   webhook_secret_configured: {result.webhook_secret_configured}")
        if result.checkout_http_status is not None:
            print(f"   checkout_http_status: {result.checkout_http_status}")
        if result.webhook_http_status is not None:
            print(f"   webhook_http_status: {result.webhook_http_status}")
        print(f"   detail: {result.detail}")

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
