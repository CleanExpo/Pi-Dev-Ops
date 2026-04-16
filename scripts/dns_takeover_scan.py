#!/usr/bin/env python3
"""
dns_takeover_scan.py — detect dangling subdomain CNAMEs across the portfolio.

Purpose
-------
Google's SEO team documented a real attack pattern: a legacy `www` DNS entry
pointed at a decommissioned Azure web app, the name got released, an attacker
grabbed it, and every visitor to `www.example.com` was redirected to a spam
site with valid SSL. Manual action + 24h of stress until reconsideration.

This scanner walks `.harness/projects.json`, extracts custom domains, and for
each domain probes BOTH the apex and the `www` variant. It flags:

  1. CNAMEs pointing at cloud app-platform hostnames where the endpoint
     returns TLS handshake failure (SNI error) or HTTP 404 — indicating the
     upstream app is dead and the name is a takeover risk.

  2. Apex/www pairs where apex works but www fails — even without a risky
     CNAME, the asymmetry means `www.` is a broken surface the site owner
     probably isn't monitoring.

A Telegram alert fires when any finding has severity >= warn.

Design choices
--------------
* Zero third-party deps — uses `socket`, `ssl`, and `urllib` from stdlib.
* Runs self-contained — no FastAPI, no MCP. Suitable for cron / GitHub Action /
  scheduled-task watchdog.
* Exit code 0 = all clear, 1 = findings, 2 = scanner itself failed.
* All findings are printed as JSON lines to stdout so downstream tooling
  (jq, log ingest, Linear auto-ticket) can parse cleanly.

Exit codes
----------
    0 — scan ran, no findings
    1 — scan ran, at least one finding at warn+ severity
    2 — scanner failed (unreadable projects.json, etc.)
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

# Cloud app-platform suffixes that auto-provision certs for any CNAME-verified
# custom domain. A dangling CNAME to any of these is a takeover vector the
# moment the underlying app is deleted and the name recycled.
RISKY_SUFFIXES = (
    ".ondigitalocean.app",
    ".azurewebsites.net",
    ".herokuapp.com",
    ".elasticbeanstalk.com",
    ".cloudfront.net",
    ".s3.amazonaws.com",
    ".s3-website.amazonaws.com",
    ".github.io",
    ".netlify.app",
    ".pages.dev",
    ".fly.dev",
    ".up.railway.app",  # Railway released subdomain names are a real takeover vector
    ".render.com",
    ".onrender.com",
    ".firebaseapp.com",
    ".web.app",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT_ROOT / ".harness" / "projects.json"


@dataclass
class Finding:
    domain: str
    hostname: str         # apex or www.apex
    severity: str         # info | warn | critical
    kind: str             # cname-to-platform, tls-handshake-fail, www-only-broken, …
    detail: str
    cname_target: Optional[str] = None
    http_status: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# DNS helpers — stdlib only
# ─────────────────────────────────────────────────────────────────────────────
def resolve_cname(host: str) -> Optional[str]:
    """Return the CNAME target for `host`, or None if no CNAME (A record only).

    socket.getaddrinfo does not expose CNAMEs directly. We shell out to the
    system `dig` when available; otherwise we rely on aliaslist from
    socket.gethostbyname_ex.
    """
    import shutil, subprocess
    if shutil.which("dig"):
        try:
            out = subprocess.check_output(
                ["dig", "+short", host, "CNAME"], timeout=8, text=True
            ).strip()
            if out:
                # dig prints the target with trailing dot, e.g. "target.example."
                return out.splitlines()[0].rstrip(".")
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return None
        return None
    # Fallback — no CNAME visibility, just return None (A-only resolution)
    try:
        host_name, aliaslist, _ = socket.gethostbyname_ex(host)
        for a in aliaslist:
            if a != host:
                return a.rstrip(".")
    except socket.gaierror:
        pass
    return None


def probe_tls(host: str, timeout: float = 6.0) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means the TLS handshake failed for SNI=host."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                if not cert:
                    return False, "no peer cert"
                return True, "ok"
    except ssl.SSLError as e:
        return False, f"ssl: {e.reason or e}"
    except (socket.timeout, OSError) as e:
        return False, f"net: {e}"


def probe_http_status(host: str, timeout: float = 6.0) -> Optional[int]:
    """HEAD https://host/ and return status, or None on connection failure."""
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(f"https://{host}/", method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, socket.timeout, OSError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Scanner core
# ─────────────────────────────────────────────────────────────────────────────
def extract_custom_domains(registry: dict) -> list[str]:
    """Return unique apex domains from `deployments.frontend` urls, skipping
    platform subdomains (we only care about the customer's own apex)."""
    domains: set[str] = set()
    platform_suffixes = (".vercel.app", ".up.railway.app", ".netlify.app", ".pages.dev")
    for p in registry.get("projects", []):
        for url in (p.get("deployments") or {}).values():
            if not url:
                continue
            host = urlparse(url).netloc.lower()
            if not host:
                continue
            # Skip platform-owned subdomains — only own-apex domains carry
            # takeover risk for *this* scanner. The platform vendors protect
            # their own namespace.
            if host.endswith(platform_suffixes):
                continue
            # Strip any leading www. so we canonicalise to apex
            apex = host[4:] if host.startswith("www.") else host
            domains.add(apex)
    return sorted(domains)


def scan_hostname(apex: str, hostname: str) -> list[Finding]:
    findings: list[Finding] = []
    cname = resolve_cname(hostname)
    status = probe_http_status(hostname)
    tls_ok, tls_reason = probe_tls(hostname)

    if cname and any(cname.endswith(suf) for suf in RISKY_SUFFIXES):
        # Platform CNAME — check if the endpoint is alive under the claimed name
        if not tls_ok:
            findings.append(Finding(
                domain=apex,
                hostname=hostname,
                severity="critical",
                kind="dangling-cname",
                detail=f"CNAME → {cname} but TLS handshake fails ({tls_reason}). "
                       f"If the upstream app is deleted, this name can be claimed "
                       f"by an attacker and served with a fresh cert.",
                cname_target=cname,
                http_status=status,
            ))
        elif status is not None and status >= 400:
            findings.append(Finding(
                domain=apex,
                hostname=hostname,
                severity="warn",
                kind="platform-cname-4xx",
                detail=f"CNAME → {cname} serves HTTP {status}. "
                       f"App may be misconfigured — confirm the mapping is alive.",
                cname_target=cname,
                http_status=status,
            ))
    elif not tls_ok and hostname.startswith("www."):
        # www-only broken — apex probed separately, asymmetry is a smell
        findings.append(Finding(
            domain=apex,
            hostname=hostname,
            severity="warn",
            kind="www-tls-broken",
            detail=f"www variant TLS fails ({tls_reason}). "
                   f"If the apex works, users typing `www.` hit a dead surface "
                   f"that could be silently hijacked via DNS.",
            cname_target=cname,
            http_status=status,
        ))

    return findings


def scan(registry: dict) -> list[Finding]:
    findings: list[Finding] = []
    for apex in extract_custom_domains(registry):
        for host in (apex, f"www.{apex}"):
            findings.extend(scan_hostname(apex, host))
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Output + Telegram alert
# ─────────────────────────────────────────────────────────────────────────────
def format_alert(findings: Iterable[Finding]) -> str:
    lines = ["🚨 DNS takeover scan — findings:"]
    for f in findings:
        icon = "🔴" if f.severity == "critical" else "🟠"
        lines.append(f"{icon} {f.hostname} [{f.kind}]")
        lines.append(f"   {f.detail}")
        if f.cname_target:
            lines.append(f"   CNAME → {f.cname_target}")
    return "\n".join(lines)


def send_telegram_alert(text: str) -> None:
    """Best-effort Telegram push — swallow any failure so the scanner still
    exits cleanly with the finding count as its signal."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from send_telegram import send_telegram
        send_telegram(text)
    except Exception as exc:
        print(f"[warn] Telegram alert failed: {exc}", file=sys.stderr)


def main() -> int:
    try:
        registry = json.loads(REGISTRY.read_text())
    except Exception as exc:
        print(f"[error] Cannot read {REGISTRY}: {exc}", file=sys.stderr)
        return 2

    findings = scan(registry)

    for f in findings:
        print(json.dumps(asdict(f)))

    critical_or_warn = [f for f in findings if f.severity in ("warn", "critical")]
    if critical_or_warn:
        if os.environ.get("DNS_SCAN_TELEGRAM", "1") == "1":
            send_telegram_alert(format_alert(critical_or_warn))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
