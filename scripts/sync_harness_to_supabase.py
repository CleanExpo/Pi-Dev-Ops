#!/usr/bin/env python3
"""
sync_harness_to_supabase.py
Migrates existing Pi-CEO harness files into Supabase tables:
  - .harness/seo/*.md         → pi_ceo_seo_reports
  - .harness/security/*.md    → pi_ceo_activity (action_type='security_audit')
  - .harness/overnight-build-*.md → pi_ceo_activity (action_type='overnight_build')
  - .harness/clients/*.md     → pi_ceo_activity (action_type='client_update')
"""

import glob
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SUPABASE_URL = "https://lksfwktwtmyznckodsau.supabase.co"
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SERVICE_KEY:
    raise SystemExit(
        "ERROR: SUPABASE_SERVICE_ROLE_KEY env var is not set.\n"
        "Set it via 1Password item js76udv2l2ncapgdt27reg65hi.\n"
        "For one-shot use: SUPABASE_SERVICE_ROLE_KEY=... "
        "python3 scripts/sync_harness_to_supabase.py\n"
        "RA-3034: hardcoded fallback removed; key rotation is tracked in RA-2989."
)
HARNESS_DIR = Path("/Users/phill-mac/Pi-Dev-Ops/.harness")


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    print(f"[{now_utc()}] {msg}")


def supabase_post(table, payload, prefer="return=minimal"):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}",
        data=data,
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def supabase_upsert(table, payload, on_conflict):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}",
        data=data,
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": f"resolution=merge-duplicates,return=minimal",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_date_from_filename(stem):
    """Try to extract a date string like 2026-05-08 from a filename stem."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    return m.group(1) if m else None


# ── SEO reports → pi_ceo_seo_reports ─────────────────────────────────────────

def sync_seo_reports():
    seo_files = sorted((HARNESS_DIR / "seo").glob("*.md"))
    synced = 0
    errors = 0
    for path in seo_files:
        stem = path.stem
        content = read_file(path)
        # Derive domain from filename: ccw-keyword-gap-2026-05-08 → ccw
        # Best guess: first segment before a date or known suffixes
        parts = stem.split("-")
        # Find where the date starts (4-digit year)
        domain_parts = []
        for part in parts:
            if re.match(r"^\d{4}$", part):
                break
            domain_parts.append(part)
        domain = "-".join(domain_parts) if domain_parts else stem

        date_str = extract_date_from_filename(stem)
        report_date = date_str if date_str else now_utc()[:10]

        # Determine report_type from filename keywords
        stem_lower = stem.lower()
        if "keyword" in stem_lower:
            report_type = "keyword_gap"
        elif "semrush" in stem_lower:
            report_type = "semrush_audit"
        elif "overnight" in stem_lower or "seo-report" in stem_lower:
            report_type = "overnight_seo"
        else:
            report_type = "seo_report"

        payload = {
            "domain": domain,
            "report_type": report_type,
            "content": content,
            "metadata": {"filename": path.name, "report_date": report_date},
        }
        try:
            supabase_post("pi_ceo_seo_reports", payload)
            log(f"  SEO upserted: {path.name} (domain={domain})")
            synced += 1
        except Exception as e:
            log(f"  ERROR SEO {path.name}: {e}")
            errors += 1
    return synced, errors


# ── Security audits → pi_ceo_activity ────────────────────────────────────────

def sync_security_audits():
    sec_files = sorted((HARNESS_DIR / "security").glob("*.md"))
    synced = 0
    errors = 0
    for path in sec_files:
        content = read_file(path)
        payload = {
            "action_type": "security_audit",
            "project_id": "portfolio",
            "title": path.stem.replace("-", " ").title(),
            "detail": content[:2000],
            "url": None,
        }
        try:
            supabase_post("pi_ceo_activity", payload)
            log(f"  Security upserted: {path.name}")
            synced += 1
        except Exception as e:
            log(f"  ERROR security {path.name}: {e}")
            errors += 1
    return synced, errors


# ── Overnight builds → pi_ceo_activity ───────────────────────────────────────

def sync_overnight_builds():
    build_files = sorted(HARNESS_DIR.glob("overnight-build-*.md"))
    synced = 0
    errors = 0
    for path in build_files:
        content = read_file(path)
        date_str = extract_date_from_filename(path.stem)
        payload = {
            "action_type": "overnight_build",
            "project_id": "portfolio",
            "title": f"Overnight build — {date_str or path.stem}",
            "detail": content[:2000],
            "url": None,
        }
        try:
            supabase_post("pi_ceo_activity", payload)
            log(f"  Overnight build upserted: {path.name}")
            synced += 1
        except Exception as e:
            log(f"  ERROR overnight {path.name}: {e}")
            errors += 1
    return synced, errors


# ── Client updates → pi_ceo_activity ─────────────────────────────────────────

def sync_client_updates():
    client_files = sorted((HARNESS_DIR / "clients").glob("*.md"))
    synced = 0
    errors = 0
    for path in client_files:
        content = read_file(path)
        # Derive client name from filename prefix
        parts = path.stem.split("-")
        # First 2 parts typically form client name, e.g. bulcs-holdings
        client_name = "-".join(parts[:2]) if len(parts) >= 2 else path.stem
        payload = {
            "action_type": "client_update",
            "project_id": client_name,
            "title": path.stem.replace("-", " ").title(),
            "detail": content[:2000],
            "url": None,
        }
        try:
            supabase_post("pi_ceo_activity", payload)
            log(f"  Client update upserted: {path.name}")
            synced += 1
        except Exception as e:
            log(f"  ERROR client {path.name}: {e}")
            errors += 1
    return synced, errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Harness → Supabase Sync")
    print(f"Time: {now_utc()}")
    print("=" * 60)

    log("Syncing SEO reports…")
    seo_ok, seo_err = sync_seo_reports()

    log("Syncing security audits…")
    sec_ok, sec_err = sync_security_audits()

    log("Syncing overnight builds…")
    build_ok, build_err = sync_overnight_builds()

    log("Syncing client updates…")
    client_ok, client_err = sync_client_updates()

    total_ok = seo_ok + sec_ok + build_ok + client_ok
    total_err = seo_err + sec_err + build_err + client_err

    print()
    print("=" * 60)
    print("SUMMARY")
    print(f"  SEO reports:      {seo_ok} synced, {seo_err} errors")
    print(f"  Security audits:  {sec_ok} synced, {sec_err} errors")
    print(f"  Overnight builds: {build_ok} synced, {build_err} errors")
    print(f"  Client updates:   {client_ok} synced, {client_err} errors")
    print(f"  TOTAL:            {total_ok} synced, {total_err} errors")
    print("=" * 60)


if __name__ == "__main__":
    main()
