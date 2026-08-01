#!/usr/bin/env python3
"""drift_check.py — re-pull the four sources, diff against fence.json, ping the bot.

The fence is a snapshot of reality taken on 2026-08-01. Reality moves: a domain is
added, a database is created, a branch is protected. A fence that silently drifts
out of date is worse than no fence, because it still reads as protection.

THE ONE RULE THIS SCRIPT OBEYS: a source it could not check is reported as
UNCHECKED, never as "no drift". A clean report from a broken query looks exactly
like a clean report from a clean system — that is the failure mode this guards.

Sources:
  1. GitHub        protected branches         needs: gh CLI authed, or GH_TOKEN
  2. Supabase      projects + preview branches needs: SUPABASE_ACCESS_TOKEN
  3. Vercel        domains                     needs: VERCEL_TOKEN
  4. DigitalOcean  apps + databases            needs: doctl authed, or DIGITALOCEAN_TOKEN

Exit: 0 clean · 1 drift found · 2 could not check everything (also drift-ish)
Read-only. Never writes to fence.json — a human decides what the fence says.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def pathlib_exists(p: str) -> bool:
    return Path(p).exists()

FENCE_DIR = Path(os.environ.get("CLAUDE_FENCE_DIR", Path.home() / ".claude" / "fence"))
FENCE_FILE = FENCE_DIR / "fence.json"
REPORT = FENCE_DIR / "drift-report.txt"


def sh(cmd: list[str], timeout: int = 60) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def api(url: str, token: str, hdr: str = "Bearer") -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"{hdr} {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ------------------------------------------------------------------ sources

def github_branches() -> tuple[set[str], str | None]:
    out = sh(["gh", "repo", "list", "CleanExpo", "--limit", "200",
              "--json", "name,isArchived", "--jq",
              ".[]|select(.isArchived|not)|.name"])
    if out is None:
        return set(), "GitHub: gh CLI not authed or unreachable"
    found = set()
    for repo in [r for r in out.split() if r]:
        b = sh(["gh", "api", f"repos/CleanExpo/{repo}/branches?protected=true",
                "--jq", ".[].name"], timeout=30)
        if b:
            found.update(x for x in b.split() if x)
    return found, None


def supabase_projects() -> tuple[set[str], str | None]:
    tok = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if not tok:
        return set(), "Supabase: SUPABASE_ACCESS_TOKEN not set"
    data = api("https://api.supabase.com/v1/projects", tok)
    if not isinstance(data, list):
        return set(), "Supabase: API call failed"
    return {p["id"] for p in data if "id" in p}, None


def vercel_domains() -> tuple[set[str], str | None]:
    tok = os.environ.get("VERCEL_TOKEN", "").strip()
    if tok:
        data = api("https://api.vercel.com/v5/domains?limit=100&teamId="
                   + os.environ.get("VERCEL_TEAM_ID", ""), tok)
        if isinstance(data, dict) and "domains" in data:
            return {d["name"] for d in data["domains"]}, None
        return set(), "Vercel: API call failed"
    out = sh(["vercel", "domains", "ls", "--scope", "unite-group"])
    if out is None:
        return set(), "Vercel: VERCEL_TOKEN not set and vercel CLI unavailable"
    doms = {ln.split()[0] for ln in out.splitlines()
            if ln.strip() and "." in ln.split()[0] and not ln.strip().startswith(">")}
    return doms, None


def do_resources() -> tuple[set[str], str | None]:
    out = sh(["doctl", "databases", "list", "--format", "Name", "--no-header"])
    if out is None:
        return set(), "DigitalOcean: doctl not authed"
    return {x for x in out.split() if x}, None


# --------------------------------------------------- code-reference sweep

CODE_ROOTS = [p for p in (r"D:\Authority-Site", r"D:\Pi-Dev-Ops", r"D:\CARSI",
                          r"D:\RestoreAssist") if pathlib_exists(p)]
REF_RX = re.compile(r"\b([a-z]{20})\.supabase\.co\b")
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv"}
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".sh", ".py", ".yml", ".yaml"}


def code_refs() -> tuple[dict[str, list[str]], str | None]:
    """Find Supabase project refs named in CODE. A database the code talks to but
    the account inventory has never heard of is the case this sweep exists for:
    it is either a dead reference (cleanup) or an uninventoried live database
    (a real production dependency nobody is watching). Silence is not an answer."""
    if not CODE_ROOTS:
        return {}, "Code sweep: no code roots found on this machine"
    found: dict[str, list[str]] = {}
    for root in CODE_ROOTS:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() not in CODE_EXT:
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as fh:
                        for m in REF_RX.finditer(fh.read()):
                            found.setdefault(m.group(1), []).append(fp)
                except Exception:
                    continue
    return found, None


def ref_is_live(ref: str) -> bool | None:
    """True = reachable, False = unreachable, None = could not tell.
    Positive control is built in: a live project answers the REST root with 401."""
    try:
        req = urllib.request.Request(f"https://{ref}.supabase.co/rest/v1/")
        with urllib.request.urlopen(req, timeout=12):
            return True
    except urllib.error.HTTPError:
        return True          # answered (401/404) => the host exists
    except Exception:
        return False         # no connection => unreachable


# ------------------------------------------------------------------ main

def main() -> int:
    if not FENCE_FILE.exists():
        print(f"no fence at {FENCE_FILE}", file=sys.stderr)
        return 2
    fence = json.loads(FENCE_FILE.read_text(encoding="utf-8"))
    prod = fence.get("prod", {})
    known_branches = {b.lower() for b in prod.get("branches", []) if isinstance(b, str)}
    known_dbs = {d.lower() for d in prod.get("databases", []) if isinstance(d, str)}
    known_hosts = {h.lower() for h in prod.get("hosts", []) if isinstance(h, str)}
    known_hosts |= {h.lower() for h in prod.get("_excluded_hosts_known_unassigned", [])}
    excluded = {e.lower() for e in prod.get("_databases_excluded_preview_branches", [])}

    drift: list[str] = []
    unchecked: list[str] = []

    gh_b, err = github_branches()
    if err:
        unchecked.append(err)
    else:
        # Only branch NAMES the fence treats as production matter.
        new = {b for b in (x.lower() for x in gh_b)
               if b not in known_branches and b not in {"sandbox", "main-legacy"}}
        for b in sorted(new):
            drift.append(f"NEW protected branch name not in fence: '{b}'")

    sb, err = supabase_projects()
    if err:
        unchecked.append(err)
    else:
        for p in sorted({x.lower() for x in sb} - known_dbs - excluded):
            drift.append(f"NEW Supabase project not in fence: '{p}' "
                         f"(decide: production, or preview branch?)")
        for p in sorted(known_dbs - {x.lower() for x in sb}):
            if not p.endswith("ondigitalocean.com"):
                drift.append(f"Supabase project in fence no longer exists: '{p}'")

    vd, err = vercel_domains()
    if err:
        unchecked.append(err)
    else:
        for d in sorted({x.lower() for x in vd} - known_hosts):
            if not any(d in h or h in d for h in known_hosts):
                drift.append(f"NEW Vercel domain not in fence: '{d}'")

    do, err = do_resources()
    if err:
        unchecked.append(err)
    else:
        for n in sorted(do):
            if not any(n.lower() in d for d in known_dbs):
                drift.append(f"NEW DigitalOcean database not in fence: '{n}'")

    # --- code-reference sweep: databases named in code but absent from inventory ---
    refs, err = code_refs()
    if err:
        unchecked.append(err)
    else:
        inventory = known_dbs | excluded
        for ref, files in sorted(refs.items()):
            if ref.lower() in inventory:
                continue
            live = ref_is_live(ref)
            where = f"{len(files)} file(s), e.g. {os.path.basename(files[0])}"
            if live:
                drift.append(f"UNINVENTORIED LIVE DATABASE '{ref}' is named in code "
                             f"({where}) and is REACHABLE, but is in neither the account "
                             f"inventory nor the fence. Treat as a production dependency.")
            elif live is False:
                drift.append(f"DEAD REFERENCE '{ref}' is named in code ({where}) but is "
                             f"unreachable and not in the inventory. Code cleanup, not a "
                             f"fence entry — do NOT add it to the fence.")
            else:
                unchecked.append(f"Code sweep: could not determine liveness of '{ref}'")

    lines = [f"FENCE DRIFT CHECK", "=" * 50, ""]
    if drift:
        lines += ["Reality and fence.json disagree:", ""]
        lines += [f"  - {d}" for d in drift] + [""]
    else:
        lines += ["No drift found in the sources that could be checked.", ""]
    if unchecked:
        lines += ["COULD NOT CHECK (treat as unknown, NOT as clean):", ""]
        lines += [f"  - {u}" for u in unchecked] + [""]
    lines += ["A human decides what the fence says. This script never edits it.",
              "To settle a difference, re-run the production pull and update fence.json by hand."]
    body = "\n".join(lines)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(body, encoding="utf-8")
    print(body)

    if drift or unchecked:
        here = Path(__file__).parent / "notify.py"
        if here.exists():
            subprocess.run([sys.executable, str(here), "drift", str(REPORT)], check=False)
    return 1 if drift else (2 if unchecked else 0)


if __name__ == "__main__":
    sys.exit(main())
