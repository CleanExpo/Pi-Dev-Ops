#!/usr/bin/env python3
"""Unite-Group autonomous health check.

Runs as a Hermes cron (hourly). For each of ~25 checks emits PASS/FAIL/WARN.

Tier 1 (critical): a PASS->FAIL regression since the prior run, or a persistent Tier-1
                   failure resurfacing (immediately when the failing set changes, else
                   every REALERT_HOURS), writes the summary to stdout. Hermes delivers on
                   non-empty stdout — the exit code does not gate delivery. Exit 1 is set
                   alongside so the run is also visibly non-clean in its own job status.
Tier 2 (important): tracked but never alert.
Tier 3 (info):      logged for trend analysis.

Outputs:
  stdout                       — short Markdown summary (used by Hermes if exit != 0)
  stderr                       — verbose run log
  logs/health/unite-group-<ts>.json      — full JSON record (one per run)
  logs/health/unite-group-latest.md      — overwritten human summary

Stdlib-only (Python 3.10+).
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ── constants ──────────────────────────────────────────────────────────────────
HERMES_HOME = Path.home() / ".hermes"
ENV_FILE = HERMES_HOME / ".env"
LOG_DIR = HERMES_HOME / "logs" / "health"
LATEST_MD = LOG_DIR / "unite-group-latest.md"

SUPABASE_PROD_ID = "lksfwktwtmyznckodsau"
SUPABASE_SANDBOX_ID = "xgqwfwqumliuguzhshwv"

VERCEL_TEAM_ID = "team_KMZACI5rIltoCRhAtGCXlxUf"
VERCEL_PROJECT_ID = "prj_IfUuJNLjXTE8VXqEGwLAleIGhiA0"
VERCEL_AUTH_JSON = (
    Path.home() / "Library" / "Application Support" / "com.vercel.cli" / "auth.json"
)

USER_AGENT = "unite-group-health-check/1.0"
HTTP_TIMEOUT = 20

# Baseline numbers (recorded post-Plan-1 work — used for regression checks)
ADVISOR_BASELINE = 71
ADVISOR_BASELINE_SLACK = 5

# Integration cadences in seconds.  Each integration's `last_sync_completed_at`
# must be within 2x its cadence; if older, flag as stale.
INTEGRATION_CADENCES_SEC = {
    "github": 5 * 60,
    "vercel": 60 * 60,
    "railway": 60 * 60,
    "digitalocean": 60 * 60,
    "supabase": 60 * 60,
    "linear": 15 * 60,
    "composio": 60 * 60,
    "onepassword": 24 * 60 * 60,
    "stripe": 60 * 60,
}

# Expected row-count floors for integration tables (Tier 2 sanity)
INTEGRATION_ROW_EXPECTATIONS = {
    "integration_github_repos": (">", 0),
    "integration_vercel_projects": (">=", 12),  # ~13 portfolio projects
    "integration_railway_services": (">=", 2),
    "integration_do_apps": (">=", 2),
    "integration_supabase_projects": (">=", 13),
    "integration_linear_issues": (">", 0),
    "integration_composio_connections": (">", 0),
    "integration_onepassword_index": (">", 0),
}


# ── helpers ────────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return the 3xx itself instead of chasing it.

    urlopen installs HTTPRedirectHandler by default, so a caller never sees a 3xx —
    it sees whatever the redirect lands on. Measured against the protected preview
    deployment on 2026-08-21: the true first hop is 302 to Vercel's SSO wall, and
    http_get returned **200** with an HTML login page. An endpoint check that accepts
    that is reporting a login screen as a healthy API — the exact defect this file was
    opened to fix, recreated inside the fix for it.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_get(
    url: str,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    timeout: int = HTTP_TIMEOUT,
    follow_redirects: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, method=method, headers=hdrs)
    ctx = ssl.create_default_context()
    try:
        if follow_redirects:
            opener = urllib.request.urlopen
            with opener(req, timeout=timeout, context=ctx) as resp:
                return resp.status, dict(resp.headers), resp.read()
        # A custom opener is the only way to decline the default redirect handler.
        built = urllib.request.build_opener(
            _NoRedirect, urllib.request.HTTPSHandler(context=ctx)
        )
        with built.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


def supabase_rest(env: dict[str, str], table: str, params: str = "") -> tuple[int, int]:
    """Return (http_status, row_count). Uses Content-Range header for an exact count."""
    base = env.get("SUPABASE_UNITE_GROUP_URL", "").rstrip("/")
    key = env.get("SUPABASE_UNITE_GROUP_SERVICE_KEY", "")
    if not base or not key:
        return 0, -1
    url = f"{base}/rest/v1/{table}?select=*&limit=1"
    if params:
        url += f"&{params}"
    status, hdrs, _ = http_get(
        url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "count=exact",
            "Range-Unit": "items",
            "Range": "0-0",
        },
    )
    cr = hdrs.get("Content-Range", "*/0")
    # Content-Range looks like "0-0/83" or "*/0"
    m = re.search(r"/(\d+|\*)$", cr)
    count = int(m.group(1)) if (m and m.group(1).isdigit()) else 0
    return status, count


def supabase_rest_rows(
    env: dict[str, str], table: str, params: str, limit: int = 1
) -> tuple[int, list[dict[str, Any]]]:
    base = env.get("SUPABASE_UNITE_GROUP_URL", "").rstrip("/")
    key = env.get("SUPABASE_UNITE_GROUP_SERVICE_KEY", "")
    if not base or not key:
        return 0, []
    url = f"{base}/rest/v1/{table}?{params}&limit={limit}"
    status, _, body = http_get(
        url, headers={"apikey": key, "Authorization": f"Bearer {key}"}
    )
    try:
        return status, json.loads(body.decode("utf-8") or "[]")
    except Exception:
        return status, []


def supabase_mgmt(env: dict[str, str], path: str) -> tuple[int, Any]:
    tok = env.get("SUPABASE_ACCESS_TOKEN", "")
    if not tok:
        return 0, None
    status, _, body = http_get(
        f"https://api.supabase.com{path}",
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    try:
        return status, json.loads(body.decode("utf-8"))
    except Exception:
        return status, None


def vercel_token() -> str | None:
    try:
        return json.loads(VERCEL_AUTH_JSON.read_text()).get("token")
    except Exception:
        return None


def parse_iso(ts: str | None) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        # Postgres returns "2026-05-12T11:22:33.123+00:00" or "...Z"
        ts2 = ts.replace("Z", "+00:00")
        return _dt.datetime.fromisoformat(ts2)
    except Exception:
        return None


def unreadable_prior(crashed: bool = False) -> dict[str, Any]:
    """Truthy on purpose: `bool(prior)` is what main() uses to tell a first run from a
    later one, and an unreadable record is not a first run.

    Built fresh per call rather than copied from a module constant — a `dict(CONST)`
    shallow copy shares the `checks` list, so one caller appending to it would corrupt
    every later call in the process. No caller mutates it today; this file's whole
    history is guards that were right until they weren't.
    """
    return {"started": None, "checks": [], "unreadable": True, "crashed": crashed}


def prior_run() -> dict[str, Any] | None:
    """Load the most recent JSON report prior to this run.

    The shape check is not decoration. `json.loads("5")` succeeds, so a truncated or
    clobbered record parses cleanly into an int, and every caller then does
    `prior.get(...)` — an AttributeError that the top-level handler turns into
    `FATAL ... exit 2`, skipping the entire hour's health check. A corrupt record
    means "no usable prior run", not "no health check today".

    `isinstance(record, dict)` alone was not enough, and a reviewer caught it: both
    consumers — regressed() and check_github_commits_growth() — iterate
    `prior["checks"]` and call `.get()` on each element. A record shaped
    `{"checks": {"name": "x"}}` iterates the dict's KEYS, so `.get()` lands on a str
    and crashes exactly as before, one level deeper. The only thing either consumer
    reads is `checks`, so a record whose checks are unusable is a record with nothing
    usable in it.
    """
    files = sorted(glob.glob(str(LOG_DIR / "unite-group-*.json")))
    if not files:
        return None
    try:
        record = json.loads(Path(files[-1]).read_text())
    except Exception:
        record = None
    if isinstance(record, dict):
        checks = record.get("checks", [])
        if isinstance(checks, list) and all(isinstance(c, dict) for c in checks):
            # `record or ...` because an empty dict passes every check above and is
            # still FALSY, and main() reads `bool(prior)` to tell a first run from a
            # later one. `{}` is a record that exists, so it must not read as absent —
            # the fifth door into the same silencing bug, this one through truthiness
            # rather than a type.
            return record or unreadable_prior()
    # A record exists but cannot be read. Returning None here said "there was no prior
    # run", which sends main() down the baseline path: alert is `bool(prior) and ...`,
    # so a live Tier-1 failure went out SILENT at exit 0. Two reviewers caught it, and
    # it is worse than the crash it replaced — exit 2 at least showed up in the cron
    # store as last_status=error, visible to the sweep in this same branch.
    # UNREADABLE_PRIOR means "a run happened, we know nothing about its checks": no
    # regression can be computed, but persistent-failure resurfacing still fires.
    return unreadable_prior()


# ── check primitives ───────────────────────────────────────────────────────────
# A regression-only alarm goes silent the moment a failure becomes steady-state, so a
# permanently-down endpoint is reported once and never again. `unite api/health` was
# returning 503 for months with nothing saying so. Persistent Tier-1 failures now
# resurface: immediately if the failing set changes, otherwise every REALERT_HOURS.
ALERT_STATE = LOG_DIR / "alert-state.json"
REALERT_HOURS = float(os.environ.get("UG_HEALTH_REALERT_HOURS", "6"))


def should_resurface(tier1_failing: list[str]) -> tuple[bool, str]:
    """Should a persistent (non-regression) Tier-1 failure be re-announced?"""
    if not tier1_failing:
        return False, ""
    # Sort both sides here rather than trusting the caller — comparing a sorted stored
    # signature against an unsorted argument reports "changed" on every run, which turns
    # the 6h throttle into no throttle at all.
    current = sorted(tier1_failing)
    try:
        state = json.loads(ALERT_STATE.read_text())
    except (OSError, ValueError):
        return True, "no prior alert state"
    if not isinstance(state, dict):
        # A bare scalar is valid JSON, so it slips past the decode guard above and
        # reaches `.get()`. Unreadable state already means "alert" — a corrupt file
        # must take the same route, not crash the run that was about to alert.
        return True, "unreadable alert state"
    stored = state.get("signature") or []
    if not isinstance(stored, list) or any(not isinstance(x, str) for x in stored):
        # Right container, wrong contents: `sorted(5)` raises TypeError, and so does
        # `sorted(["x", 5])` — '<' not supported between int and str. Either aborts the
        # run BEFORE stdout is written, suppressing the very alert it was deciding
        # about. The element check is the third time in this file that guarding the
        # container turned out not to be guarding the value.
        return True, "unreadable alert state signature"
    if sorted(stored) != current:
        return True, "failing set changed"
    try:
        last = _dt.datetime.fromisoformat(state["last_alert_at"])
    except (KeyError, ValueError, TypeError):
        # TypeError, not just ValueError: fromisoformat raises TypeError on a non-str,
        # so a numeric or null last_alert_at escaped this handler. Fourth time in this
        # file that a guard covered the container and not the value.
        return True, "unreadable last_alert_at"
    hours = (_dt.datetime.now(_dt.timezone.utc) - last).total_seconds() / 3600
    if hours >= REALERT_HOURS:
        return True, f"{hours:.1f}h since last alert"
    return False, ""


def note_alert(tier1_failing: list[str]) -> None:
    try:
        ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_STATE.write_text(json.dumps({
            "last_alert_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "signature": tier1_failing,
        }, indent=1))
    except OSError as e:  # never let bookkeeping break the check
        log(f"could not write alert state: {e}")


def mk(
    name: str, tier: int, status: str, detail: str, **extra: Any
) -> dict[str, Any]:
    """status ∈ {PASS, FAIL, WARN, SKIP}."""
    rec = {"name": name, "tier": tier, "status": status, "detail": detail}
    if extra:
        rec["data"] = extra
    return rec


# ── tier 1 ─────────────────────────────────────────────────────────────────────
def check_http(name: str, url: str, tier: int = 1) -> dict[str, Any]:
    try:
        t0 = time.time()
        status, _, _ = http_get(url, timeout=15)
        ms = int((time.time() - t0) * 1000)
        if 200 <= status < 400:
            return mk(name, tier, "PASS", f"{status} in {ms}ms", code=status, ms=ms)
        return mk(name, tier, "FAIL", f"HTTP {status} ({ms}ms)", code=status, ms=ms)
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        return mk(name, tier, "FAIL", f"unreachable: {type(e).__name__}")
    except Exception as e:
        return mk(name, tier, "FAIL", f"error: {type(e).__name__}: {e}")


# HEAD is not universally implemented. A 404/405 from it means "ask again with GET",
# never "healthy" — but both were excluded from the fallback condition below, so a HEAD
# 404 skipped the GET entirely and then cleared a sub-500 accept band as a PASS. This
# check reported green on a missing endpoint: the exact failure it exists to catch.
_HEAD_RETRY_CODES = frozenset({0, 404, 405})


def check_unite_health_api(url: str) -> dict[str, Any]:
    # follow_redirects=False so a 3xx is SEEN as a 3xx. With the default handler this
    # check followed an auth wall to a 200 HTML login page and called it healthy.
    try:
        status, _, _ = http_get(url, method="HEAD", timeout=15, follow_redirects=False)
    except Exception:
        status = 0
    if status in _HEAD_RETRY_CODES or status >= 500:
        try:
            status, _, _ = http_get(url, method="GET", timeout=15, follow_redirects=False)
        except Exception:
            # code=0 for shape consistency with every other return here; no consumer
            # reads it, so this is tidiness rather than a fix.
            return mk("unite api/health", 1, "FAIL", "unreachable", code=0)
    # 2xx only. A 3xx here is a redirect away from the endpoint or an auth wall, not a
    # health report — the preview deployment answering 302 behind Vercel protection is
    # precisely the read that must not count as healthy.
    if 200 <= status < 300:
        return mk("unite api/health", 1, "PASS", f"HTTP {status}", code=status)
    return mk("unite api/health", 1, "FAIL", f"HTTP {status}", code=status)


def check_supabase_status(env: dict[str, str]) -> dict[str, Any]:
    status, data = supabase_mgmt(env, f"/v1/projects/{SUPABASE_PROD_ID}")
    if status != 200 or not isinstance(data, dict):
        return mk(
            "supabase prod status", 1, "FAIL", f"mgmt API HTTP {status}", http=status
        )
    s = data.get("status", "?")
    if s == "ACTIVE_HEALTHY":
        return mk(
            "supabase prod status", 1, "PASS", f"status={s}", project_status=s
        )
    return mk("supabase prod status", 1, "FAIL", f"status={s}", project_status=s)


def check_supabase_advisors(env: dict[str, str]) -> list[dict[str, Any]]:
    status, data = supabase_mgmt(
        env, f"/v1/projects/{SUPABASE_PROD_ID}/advisors/security"
    )
    if status != 200:
        bad = mk(
            "supabase advisor errors",
            1,
            "FAIL",
            f"mgmt API HTTP {status}",
            http=status,
        )
        return [bad, mk("supabase advisor total", 1, "FAIL", f"mgmt API HTTP {status}")]
    lints = data.get("lints") if isinstance(data, dict) else data
    if isinstance(lints, list) and any(not isinstance(x, dict) for x in lints):
        # Same class as the store guards: the advisor API is external, and one
        # non-object entry would reach `x.get("level")` and abort the whole run.
        # A response we cannot count is an unreadable response, not zero findings.
        lints = None
    if not isinstance(lints, list):
        return [
            mk("supabase advisor errors", 1, "FAIL", "no lint list in response"),
            mk("supabase advisor total", 1, "FAIL", "no lint list in response"),
        ]
    err_count = sum(
        1 for x in lints if str(x.get("level", "")).upper() == "ERROR"
    )
    total = len(lints)
    err_res = (
        mk("supabase advisor errors", 1, "PASS", f"{err_count} ERROR-level findings", count=err_count)
        if err_count == 0
        else mk(
            "supabase advisor errors", 1, "FAIL", f"{err_count} ERROR-level findings — regression", count=err_count
        )
    )
    # Drift was signed and bounded upward only, so a collapse to zero scored
    # `-71 <= 5` and read as healthy. The bound is now two-sided, and an empty list is
    # not reported as a clean read of zero findings.
    drift = total - ADVISOR_BASELINE
    if total == 0:
        tot_res = mk(
            "supabase advisor total",
            1,
            "FAIL",
            "0 findings — an empty advisor list is indistinguishable from an "
            "unreadable response, so it is not reported as a clean read",
            count=total,
            drift=drift,
        )
    elif drift > ADVISOR_BASELINE_SLACK:
        tot_res = mk(
            "supabase advisor total",
            1,
            "FAIL",
            f"{total} findings exceeds baseline+{ADVISOR_BASELINE_SLACK} (drift {drift:+d})",
            count=total,
            drift=drift,
        )
    elif drift < -ADVISOR_BASELINE_SLACK:
        # This was a WARN, to avoid an hourly Tier-1 FAIL about a sanctioned
        # improvement. A reviewer traced it and was right to object: tier1_failing
        # collects status == "FAIL" only, and regressed() likewise, so a Tier-1 WARN
        # reaches NO alert path — it lands in a JSON file nobody opens. That is the
        # deliver-to-origin failure this whole ticket exists to remove.
        # FAIL is correct, and the noise concern is already answered by the
        # REALERT_HOURS throttle: it alerts once, then every 6h until re-baselined,
        # which is the prompt to move ADVISOR_BASELINE.
        tot_res = mk(
            "supabase advisor total",
            1,
            "FAIL",
            f"{total} findings is {abs(drift)} below baseline {ADVISOR_BASELINE} — "
            f"re-baseline or investigate the source (drift {drift:+d})",
            count=total,
            drift=drift,
        )
    else:
        tot_res = mk(
            "supabase advisor total",
            1,
            "PASS",
            f"{total} findings (baseline {ADVISOR_BASELINE}, drift {drift:+d})",
            count=total,
            drift=drift,
        )
    return [err_res, tot_res]


def check_hermes_gateway() -> dict[str, Any]:
    try:
        out = subprocess.run(
            ["pgrep", "-fl", "hermes_cli.main gateway"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        return mk("hermes gateway", 1, "FAIL", f"pgrep error: {e}")
    line = out.stdout.strip()
    if line:
        pid = line.split()[0]
        return mk("hermes gateway", 1, "PASS", f"alive pid={pid}", pid=pid)
    return mk("hermes gateway", 1, "FAIL", "no process matched")


# The sanctioned model chain, not one hardcoded string. The previous single-value
# expectation (`meta-llama/llama-3.3-70b-instruct`) went stale the moment the estate
# retired Gemma and moved the chain on 2026-08-19/20, and would then have raised a
# Tier-1 regression every hour forever about a change that was deliberate. A drift
# check that fires on sanctioned change trains its reader to ignore it.
# Override with UG_HEALTH_EXPECTED_MODELS (comma-separated) when the chain moves.
_SANCTIONED_MODELS = (
    "nvidia/nemotron-3-super-120b-a12b:free",   # current default
    "dots-studio/dots-3-note-preview:free",     # free fallback
    "z-ai/glm-4.7-flash",                       # paid fallback
)


def check_hermes_model() -> dict[str, Any]:
    raw = os.environ.get("UG_HEALTH_EXPECTED_MODELS", "")
    expected = tuple(m.strip() for m in raw.split(",") if m.strip()) or _SANCTIONED_MODELS
    cfg = HERMES_HOME / "config.yaml"
    if not cfg.exists():
        return mk("hermes model", 1, "FAIL", "config.yaml missing")
    # Read first ~40 lines — the `model:` block is at the top
    txt = cfg.read_text()
    # Find the model: key and the first `default:` after it
    m = re.search(r"^model:\s*\n((?:[ \t].*\n){0,30})", txt, re.MULTILINE)
    if not m:
        return mk("hermes model", 1, "FAIL", "no model: block in config")
    block = m.group(1)
    dm = re.search(r"default:\s*(.+)", block)
    current = dm.group(1).strip().strip('"').strip("'") if dm else "?"
    if current in expected:
        return mk("hermes model", 1, "PASS", current, model=current)
    return mk(
        "hermes model",
        1,
        "FAIL",
        f"got {current!r}, not in sanctioned chain {list(expected)!r}",
        model=current,
    )


def check_integration_sync(env: dict[str, str]) -> list[dict[str, Any]]:
    status, rows = supabase_rest_rows(
        env, "integration_sync_state", "select=integration,last_sync_status,last_sync_completed_at,last_sync_error", limit=100
    )
    if status != 200:
        return [
            mk(
                f"integration sync — {name}",
                1,
                "FAIL",
                f"REST HTTP {status}",
            )
            for name in INTEGRATION_CADENCES_SEC
        ]
    by_name = {r.get("integration"): r for r in rows}
    now = _dt.datetime.now(_dt.timezone.utc)
    results: list[dict[str, Any]] = []

    for name, cadence in INTEGRATION_CADENCES_SEC.items():
        row = by_name.get(name)
        if not row:
            # Pre-first-fire: warn rather than fail, but only treat as FAIL if a
            # known-fired integration drops out.  Sync table being empty is the
            # current steady state until the 4am cron fires.
            results.append(
                mk(
                    f"integration sync — {name}",
                    1,
                    "WARN",
                    "no sync_state row yet (cron not fired)",
                    integration=name,
                )
            )
            results.append(
                mk(
                    f"integration freshness — {name}",
                    1,
                    "WARN",
                    "no sync_state row yet (cron not fired)",
                    integration=name,
                )
            )
            continue

        s = row.get("last_sync_status")
        if s == "ok":
            results.append(
                mk(
                    f"integration sync — {name}",
                    1,
                    "PASS",
                    "last_sync_status=ok",
                    integration=name,
                )
            )
        else:
            results.append(
                mk(
                    f"integration sync — {name}",
                    1,
                    "FAIL",
                    f"last_sync_status={s!r}",
                    integration=name,
                )
            )

        ts = parse_iso(row.get("last_sync_completed_at"))
        if ts is None:
            results.append(
                mk(
                    f"integration freshness — {name}",
                    1,
                    "FAIL",
                    "last_sync_completed_at missing",
                    integration=name,
                )
            )
            continue
        age = (now - ts).total_seconds()
        limit = 2 * cadence
        if age <= limit:
            results.append(
                mk(
                    f"integration freshness — {name}",
                    1,
                    "PASS",
                    f"age {int(age)}s ≤ {limit}s",
                    integration=name,
                    age_sec=int(age),
                )
            )
        else:
            results.append(
                mk(
                    f"integration freshness — {name}",
                    1,
                    "FAIL",
                    f"age {int(age)}s > {limit}s — stale",
                    integration=name,
                    age_sec=int(age),
                )
            )

    return results


def check_vercel_deployment() -> dict[str, Any]:
    tok = vercel_token()
    if not tok:
        return mk("vercel prod deployment", 1, "FAIL", "no vercel auth token")
    url = (
        f"https://api.vercel.com/v6/deployments?teamId={VERCEL_TEAM_ID}"
        f"&projectId={VERCEL_PROJECT_ID}&target=production&limit=1"
    )
    status, _, body = http_get(url, headers={"Authorization": f"Bearer {tok}"})
    if status != 200:
        return mk("vercel prod deployment", 1, "FAIL", f"HTTP {status}")
    try:
        d = json.loads(body).get("deployments", [{}])[0]
    except Exception:
        return mk("vercel prod deployment", 1, "FAIL", "bad JSON")
    state = d.get("state", "?")
    if state == "READY":
        return mk(
            "vercel prod deployment", 1, "PASS", f"state={state}", state=state
        )
    return mk(
        "vercel prod deployment", 1, "FAIL", f"state={state}", state=state
    )


# ── tier 2 ─────────────────────────────────────────────────────────────────────
def check_integration_row_counts(env: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for table, (op, expected) in INTEGRATION_ROW_EXPECTATIONS.items():
        status, count = supabase_rest(env, table)
        if status not in (200, 206):
            out.append(mk(f"rows — {table}", 2, "WARN", f"REST HTTP {status}"))
            continue
        ok = (op == ">" and count > expected) or (op == ">=" and count >= expected)
        verdict = "PASS" if ok else "WARN"
        out.append(
            mk(
                f"rows — {table}",
                2,
                verdict,
                f"count={count} (expect {op} {expected})",
                count=count,
                expected=expected,
            )
        )
    return out


def check_github_commits_growth(env: dict[str, str], prior: dict[str, Any] | None) -> dict[str, Any]:
    status, count = supabase_rest(env, "integration_github_commits")
    if status not in (200, 206):
        return mk("github commit growth", 2, "WARN", f"REST HTTP {status}")
    prior_count = None
    if prior:
        for r in prior.get("checks", []):
            if r.get("name") == "github commit growth":
                prior_count = (r.get("data") or {}).get("count")
                break
            if r.get("name") == "rows — integration_github_commits":
                prior_count = (r.get("data") or {}).get("count")
    if prior_count is None:
        return mk(
            "github commit growth",
            2,
            "WARN",
            f"no prior baseline; count={count}",
            count=count,
        )
    delta = count - prior_count
    verdict = "PASS" if delta > 0 else "WARN"
    detail = f"delta {delta:+d} (was {prior_count}, now {count})"
    return mk(
        "github commit growth", 2, verdict, detail, count=count, delta=delta
    )


# ── tier 3 ─────────────────────────────────────────────────────────────────────
def check_sandbox_drift(env: dict[str, str]) -> list[dict[str, Any]]:
    status, data = supabase_mgmt(env, f"/v1/projects/{SUPABASE_SANDBOX_ID}")
    if status != 200 or not isinstance(data, dict):
        return [
            mk(
                "sandbox status",
                3,
                "WARN",
                f"mgmt API HTTP {status}",
                http=status,
            )
        ]
    s = data.get("status", "?")
    res = [mk("sandbox status", 3, "PASS" if s == "ACTIVE_HEALTHY" else "WARN", f"status={s}", project_status=s)]
    # Table count drift — list tables via mgmt API
    pst, p_tables = supabase_mgmt(
        env, f"/v1/projects/{SUPABASE_PROD_ID}/database/tables?schema=public"
    )
    sst, s_tables = supabase_mgmt(
        env, f"/v1/projects/{SUPABASE_SANDBOX_ID}/database/tables?schema=public"
    )
    if pst == 200 and sst == 200 and isinstance(p_tables, list) and isinstance(s_tables, list):
        p_n, s_n = len(p_tables), len(s_tables)
        denom = max(p_n, 1)
        pct = abs(p_n - s_n) / denom * 100
        verdict = "PASS" if pct <= 5 else "WARN"
        res.append(
            mk(
                "sandbox table drift",
                3,
                verdict,
                f"prod={p_n}, sandbox={s_n}, drift={pct:.1f}%",
                prod=p_n,
                sandbox=s_n,
                drift_pct=round(pct, 1),
            )
        )
    else:
        res.append(
            mk(
                "sandbox table drift",
                3,
                "WARN",
                f"could not list tables (prod={pst}, sandbox={sst})",
            )
        )
    return res


def check_disk_space() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in ("/var", "/tmp", str(HERMES_HOME / "logs")):
        try:
            t = shutil.disk_usage(path)
            free_gb = t.free / (1024**3)
            pct_free = t.free / t.total * 100
            verdict = "PASS" if pct_free > 10 else "WARN"
            out.append(
                mk(
                    f"disk — {path}",
                    3,
                    verdict,
                    f"{free_gb:.1f}GB free ({pct_free:.0f}%)",
                    free_gb=round(free_gb, 1),
                    pct_free=round(pct_free, 1),
                )
            )
        except Exception as e:
            out.append(mk(f"disk — {path}", 3, "WARN", f"error: {e}"))
    return out


def check_linear_in_progress(env: dict[str, str]) -> dict[str, Any]:
    key = env.get("LINEAR_API_KEY", "")
    if not key:
        return mk("linear in-progress", 3, "WARN", "LINEAR_API_KEY missing")
    q = (
        '{ issues(filter: { state: { type: { eq: "started" } } }, first: 250) '
        "{ nodes { id } } }"
    )
    try:
        data = json.dumps({"query": q}).encode()
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": key,
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
        n = len((payload.get("data") or {}).get("issues", {}).get("nodes", []))
        return mk("linear in-progress", 3, "PASS", f"{n} issues in progress", count=n)
    except Exception as e:
        return mk("linear in-progress", 3, "WARN", f"error: {type(e).__name__}: {e}")


# ── orchestrator ───────────────────────────────────────────────────────────────
def guarded(name: str, tier: int, fn: Any, *args: Any) -> list[dict[str, Any]]:
    """Run one check. No single check may abort the run.

    Six of the defects found in this file across four review rounds were the same
    shape: some input — an HTTP response, a JSON store, a config file, a DNS lookup —
    raised out of one check, hit the top-level handler in __main__, and took the whole
    hour's monitoring with it. Exit 2 with empty stdout means the other fourteen checks
    never ran and nobody was told anything.

    Fixing each instance one at a time is what produced those four rounds. A crashed
    check is now a Tier-1 FAIL naming the exception, which ALERTS — strictly louder
    than the silence it replaces, and it cannot be reintroduced by the next check
    somebody adds.
    """
    try:
        result = fn(*args)
    except Exception as e:  # noqa: BLE001 — the point is that nothing escapes
        log(f"check {name!r} crashed: {type(e).__name__}: {e}")
        return [mk(name, tier, "FAIL", f"check crashed: {type(e).__name__}: {e}",
                   crashed=True)]
    return result if isinstance(result, list) else [result]


# Named so it is visible in the delivered alert rather than looking like a check.
REGRESSION_CHECK_FAILED = "<regression check failed — treating as a regression>"


def never_fatal(label: str, fn: Any, fallback: Any) -> Any:
    """Run one step of main()'s alert path. Nothing here may stop the alert.

    `guarded` protects the checks; this protects everything between them and stdout.
    Three separate defects have now landed in that stretch — a TypeError parsing
    last_alert_at, and an OSError writing the JSON record — each aborting main() AFTER
    the work was done and BEFORE the alert went out. A run that looks complete on disk
    and told nobody is the worst outcome this file can produce, worse than crashing
    early, because the cron store still shows it ran.

    The record on disk is a convenience. The alert is the product.
    """
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — that is the entire point
        log(f"{label} failed ({type(e).__name__}: {e}) — continuing so the alert goes out")
        return fallback


def run_all() -> list[dict[str, Any]]:
    # The first line of the run was the one unguarded step left. An unreadable
    # ~/.hermes/.env raised out of here before a single check executed, so the run
    # ended at exit 2 with nothing said about anything. An empty env is honest: the
    # credentialed checks then fail on their own and say why.
    env = never_fatal("load_env", load_env, {})
    checks: list[dict[str, Any]] = []

    # Tier 1
    log("Tier 1: HTTP endpoints")
    checks += guarded("unite-group.in /", 1,
                      check_http, "unite-group.in /", "https://unite-group.in/", 1)
    checks += guarded("unite-group.in /en/login", 1,
                      check_http, "unite-group.in /en/login",
                      "https://unite-group.in/en/login", 1)
    checks += guarded("unite api/health", 1,
                      check_unite_health_api, "https://unite-group.in/api/health")

    log("Tier 1: Supabase prod status + advisors")
    checks += guarded("supabase status", 1, check_supabase_status, env)
    checks += guarded("supabase advisors", 1, check_supabase_advisors, env)

    log("Tier 1: Hermes gateway + model")
    checks += guarded("hermes gateway", 1, check_hermes_gateway)
    checks += guarded("hermes model", 1, check_hermes_model)

    log("Tier 1: integration cron sync state")
    checks += guarded("integration sync", 1, check_integration_sync, env)

    log("Tier 1: Vercel production deployment")
    checks += guarded("vercel production deployment", 1, check_vercel_deployment)

    # Tier 2
    log("Tier 2: integration row counts + growth")
    checks += guarded("integration row counts", 2, check_integration_row_counts, env)
    prior = prior_run()
    checks += guarded("github commit growth", 2, check_github_commits_growth, env, prior)

    # Tier 3
    log("Tier 3: sandbox drift, disk, Linear in-progress")
    checks += guarded("sandbox drift", 3, check_sandbox_drift, env)
    checks += guarded("disk space", 3, check_disk_space)
    checks += guarded("linear in-progress", 3, check_linear_in_progress, env)

    return checks


def regressed(checks: list[dict[str, Any]], prior: dict[str, Any] | None) -> list[str]:
    """Return names of Tier-1 checks that were PASS previously and are FAIL now."""
    if not prior:
        return []
    if prior.get("crashed"):
        # No baseline can be computed and the store itself failed. Reporting "no
        # regressions" here is a false all-clear that the resurface throttle will then
        # silence — the same wrong-direction fallback a reviewer caught in `regressed`.
        return [REGRESSION_CHECK_FAILED] if any(
            c.get("tier") == 1 and c.get("status") == "FAIL" for c in checks
        ) else []
    # Subscripts, not .get() — a Tier-1 entry missing either key raises KeyError here,
    # and one whose "name" is a list raises TypeError when used as a dict key. prior_run
    # screens entry TYPE, not the type of what is inside an entry, so both routes reach
    # this comprehension. Requiring str for both closes them together: an entry we
    # cannot read is an entry with no prior status, which the comparison below handles.
    prior_status = {
        r["name"]: r["status"]
        for r in prior.get("checks", [])
        if r.get("tier") == 1
        and isinstance(r.get("name"), str)
        and isinstance(r.get("status"), str)
    }
    out: list[str] = []
    for c in checks:
        if c.get("tier") != 1:
            continue
        if c.get("status") == "FAIL" and prior_status.get(c["name"]) == "PASS":
            out.append(c["name"])
    return out


def write_outputs(
    checks: list[dict[str, Any]],
    regressions: list[str],
    started: _dt.datetime,
    finished: _dt.datetime,
) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "PASS": sum(1 for c in checks if c["status"] == "PASS"),
        "FAIL": sum(1 for c in checks if c["status"] == "FAIL"),
        "WARN": sum(1 for c in checks if c["status"] == "WARN"),
        "SKIP": sum(1 for c in checks if c["status"] == "SKIP"),
        "total": len(checks),
    }
    by_tier = {
        t: {
            "PASS": sum(1 for c in checks if c["tier"] == t and c["status"] == "PASS"),
            "FAIL": sum(1 for c in checks if c["tier"] == t and c["status"] == "FAIL"),
            "WARN": sum(1 for c in checks if c["tier"] == t and c["status"] == "WARN"),
            "total": sum(1 for c in checks if c["tier"] == t),
        }
        for t in (1, 2, 3)
    }

    record = {
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "duration_sec": round((finished - started).total_seconds(), 2),
        "host": socket.gethostname(),
        "summary": summary,
        "by_tier": by_tier,
        "regressions": regressions,
        "checks": checks,
    }

    ts_slug = started.strftime("%Y-%m-%dT%H%M%S")
    json_path = LOG_DIR / f"unite-group-{ts_slug}.json"
    json_path.write_text(json.dumps(record, indent=2, default=str))

    # Markdown summary
    def emoji(s: str) -> str:
        return {"PASS": "✓", "FAIL": "✗", "WARN": "!", "SKIP": "-"}.get(s, "?")

    md = [f"# Unite-Group health check — {started.strftime('%Y-%m-%d %H:%M:%S %Z').strip()}"]
    md.append("")
    md.append(
        f"**Summary:** {summary['PASS']} pass · {summary['FAIL']} fail · "
        f"{summary['WARN']} warn · {summary['total']} total "
        f"({record['duration_sec']}s)"
    )
    if regressions:
        md.append("")
        md.append("**Regressions vs prior run (Tier 1 PASS→FAIL):**")
        for r in regressions:
            md.append(f"- {r}")
    md.append("")
    for tier in (1, 2, 3):
        label = {1: "Tier 1 — Critical", 2: "Tier 2 — Important", 3: "Tier 3 — Info"}[tier]
        s = by_tier[tier]
        md.append(
            f"## {label} ({s['PASS']}/{s['total']} pass, {s['FAIL']} fail, {s['WARN']} warn)"
        )
        for c in checks:
            if c["tier"] != tier:
                continue
            md.append(f"- {emoji(c['status'])} **{c['status']}** {c['name']} — {c['detail']}")
        md.append("")
    LATEST_MD.write_text("\n".join(md))

    return json_path


def stdout_report(
    checks: list[dict[str, Any]],
    regressions: list[str],
    json_path: Path,
    alert: bool,
) -> None:
    """Print to stdout ONLY when we want Hermes to deliver to Telegram.

    Hermes --no-agent cron treats empty stdout as silent, and delivers whatever is
    printed regardless of exit code.  We stay quiet unless a Tier-1 check regressed
    from PASS->FAIL, or a persistent Tier-1 failure is due to resurface.
    """
    if not alert:
        return

    tier1_fail = [c for c in checks if c["tier"] == 1 and c["status"] == "FAIL"]
    total_fail = sum(1 for c in checks if c["status"] == "FAIL")
    total_warn = sum(1 for c in checks if c["status"] == "WARN")
    total_pass = sum(1 for c in checks if c["status"] == "PASS")

    print("Unite-Group health REGRESSION detected")
    print(
        f"{total_pass} pass · {total_fail} fail · {total_warn} warn "
        f"({len(checks)} checks total)"
    )
    print("")
    print(f"Regressions (Tier-1 PASS→FAIL since prior run): {len(regressions)}")
    for r in regressions:
        if r == REGRESSION_CHECK_FAILED:
            print(f"  • {r}")
            continue
        # Find the current detail line
        for c in checks:
            if c["name"] == r:
                print(f"  • {r} — {c['detail']}")
                break
    if tier1_fail and len(tier1_fail) > len(regressions):
        print("")
        print(f"All current Tier-1 failures ({len(tier1_fail)}):")
        for c in tier1_fail:
            print(f"  • {c['name']} — {c['detail']}")
    print("")
    print(f"Full report: {json_path}")
    print(f"Latest summary: {LATEST_MD}")


def main() -> int:
    started = _dt.datetime.now(_dt.timezone.utc)
    log(f"Unite-Group health check starting — {started.isoformat()}")

    # prior_run guards its own JSON parse, but the glob and the sort around it are not
    # inside that handler — and the invariant should not rest on one function's
    # internals anyway. A parametrised test breaks each step of this path in turn.
    # crashed=True distinguishes "the store is broken" from "one record was corrupt".
    # A corrupt record is handled and may be throttled; prior_run itself raising is a
    # malfunction of the monitor, and regressed() turns that into a forced alert.
    prior = never_fatal("prior_run", prior_run, unreadable_prior(crashed=True))
    if prior and prior.get("unreadable"):
        log("prior run UNREADABLE — no regression baseline, but alerting stays live")
    elif prior:
        log(f"prior run loaded: {prior.get('started')}")
    else:
        log("no prior run found — this is the baseline")

    # Belt and braces for the first link, matching the last: if the whole check run
    # fails for any reason at all, that is itself the most important thing to report.
    checks = never_fatal(
        "run_all",
        run_all,
        [mk("health check run", 1, "FAIL", "the check run itself failed", crashed=True)],
    )
    finished = _dt.datetime.now(_dt.timezone.utc)
    # Every never_fatal fallback must point TOWARD alerting. This one did not: `[]`
    # reads as "no regression", and with the resurface throttle active that produced
    # exit 0 and silence on a live failure — the wrapper written to guarantee delivery,
    # handed a fallback that suppressed it. A reviewer caught it. The sentinel is
    # truthy, so `alert` fires, and it names itself in the report rather than pretending
    # a regression was computed.
    regressions = never_fatal(
        "regressed", lambda: regressed(checks, prior), [REGRESSION_CHECK_FAILED]
    )

    json_path = never_fatal(
        "write_outputs",
        lambda: write_outputs(checks, regressions, started, finished),
        Path("<not written>"),
    )

    tier1_failing = sorted(
        c["name"] for c in checks if c["tier"] == 1 and c["status"] == "FAIL"
    )
    tier1_fail_now = bool(tier1_failing)
    # Not knowing whether to alert is a reason to alert, never a reason to go quiet.
    resurface, why = never_fatal(
        "should_resurface",
        lambda: should_resurface(tier1_failing),
        (bool(tier1_failing), "alert-state unusable"),
    )
    alert = bool(prior) and (bool(regressions) or resurface)

    # never_fatal keeps main() alive, but staying alive is not the goal — reaching
    # Hermes is. If stdout_report dies before its first print, the alert is DECIDED
    # (alert=True, exit 1) and never EMITTED, and Hermes delivers on stdout content,
    # not on exit code. Last link in the chain: emit a minimal alert ourselves.
    emitted = never_fatal(
        "stdout_report",
        lambda: (stdout_report(checks, regressions, json_path, alert), True)[1],
        False,
    )
    if alert and not emitted:
        print("Unite-Group health ALERT — report generation failed, raw list follows")
        for c in checks:
            if c.get("tier") == 1 and c.get("status") == "FAIL":
                print(f"  • {c.get('name')} — {c.get('detail')}")

    if not prior:
        log("baseline run; stdout silent, exit 0")
        return 0
    if regressions:
        note_alert(tier1_failing)
        log(f"REGRESSION detected: {regressions} — stdout active, exit 1")
        return 1
    if resurface:
        note_alert(tier1_failing)
        log(f"PERSISTENT Tier-1 failure resurfaced ({why}): {tier1_failing} "
            "— stdout active, exit 1")
        return 1
    if tier1_fail_now:
        log("Tier-1 failures present, already alerted recently and unchanged — silent, exit 0")
    else:
        log("all Tier-1 healthy — silent, exit 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("interrupted")
        sys.exit(130)
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(2)
