#!/usr/bin/env python3
"""Guardian watcher (2026-10-26). No AI model, no paid APIs, read-only checks.
Checks the live sites, the /grow + /cards buy links, and every open PR of the watched repos (via the GitHub CLI).
Each check has THREE states: OK, FAIL (a real answer that is wrong) or UNKNOWN (the check could not run:
DNS/TLS/connection/timeout, CLI missing/failing/timing out/unparsable). UNKNOWN never resets a FAIL row to done,
and after 30 minutes it escalates to "check could not run: <reason>" (different from "site down").
Writes one job per non-OK check into ops/jobs.json (ids W-*) under the shared jobs_lock, done when it recovers.
Rows carry check_state, last_known_good_at and unknown_since. Only touches its own W-* entries.
Env seams (tests): GUARDIAN_OPS, GUARDIAN_UG_BASE, GUARDIAN_SYNTHEX_BASE, GUARDIAN_GH, GUARDIAN_REPOS (comma list),
GUARDIAN_HEARTBEAT, GUARDIAN_STATE, GUARDIAN_HTTP_TIMEOUT, GUARDIAN_GH_TIMEOUT."""
import json, os, subprocess, sys, urllib.request, urllib.error, datetime, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs_lock
OPS = os.environ.get("GUARDIAN_OPS", "/Volumes/Mini Mini 2T Storage/ops")
GH = os.environ.get("GUARDIAN_GH", "/opt/homebrew/bin/gh")
UG = os.environ.get("GUARDIAN_UG_BASE", "https://unite-group.in").rstrip("/")
SX = os.environ.get("GUARDIAN_SYNTHEX_BASE", "https://synthex.social").rstrip("/")
REPOS = [r for r in os.environ.get("GUARDIAN_REPOS", "CleanExpo/Unite-Group,CleanExpo/Synthex").split(",") if r]
HEARTBEAT = os.environ.get("GUARDIAN_HEARTBEAT", os.path.join(OPS, ".watcher-last-run"))
STATE = os.environ.get("GUARDIAN_STATE", os.path.expanduser("~/.local/state/guardian-watcher.json"))
HTTP_TIMEOUT = float(os.environ.get("GUARDIAN_HTTP_TIMEOUT", "20"))
GH_TIMEOUT = float(os.environ.get("GUARDIAN_GH_TIMEOUT", "60"))
ESCALATE_AFTER = datetime.timedelta(minutes=30)
PR_LIMIT = 500   # gh pr list returns at most --limit rows (default 30); a full page never proves a PR closed
CHECK_FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
CHECK_FINAL = {"SUCCESS", "NEUTRAL", "SKIPPED", "STALE"} | CHECK_FAILED   # a COMPLETED run has one of these
CHECK_RUNNING = {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED"}   # ... and these have none yet
CHECK_PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}   # the only conclusions that count towards OK
STATUS_STATES = {"SUCCESS", "PENDING", "EXPECTED", "FAILURE", "ERROR"}
STATUS_FAILED = {"FAILURE", "ERROR"}
STATUS_PASSED = {"SUCCESS"}
TS = "%Y-%m-%dT%H:%M%z"
NOW = datetime.datetime.now().astimezone().strftime(TS)
OK, FAIL, UNKNOWN = "OK", "FAIL", "UNKNOWN"
CLOSED = "_closed_prefix_"

def get(url):
    """(status, body). status 0 = no HTTP answer at all (DNS/TLS/connect/timeout); body is then the reason."""
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "guardian-watcher"}), timeout=HTTP_TIMEOUT)
        return r.status, r.read(400000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        reason = getattr(e, "reason", None) or e
        return 0, f"{type(e).__name__}: {reason}"

def cli(*args):
    """(ok, stdout, reason). reason = first line of stderr / timeout / spawn error."""
    try:
        r = subprocess.run([GH, *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "", f"gh timed out after {GH_TIMEOUT:g}s"
    except Exception as e:
        return False, "", f"gh could not run: {type(e).__name__}: {e}"
    if r.returncode != 0:
        line = next((l.strip() for l in r.stderr.splitlines() if l.strip()), "")
        return False, "", f"gh exit {r.returncode}: {line}" if line else f"gh exit {r.returncode}"
    return True, r.stdout, ""

def cli_json(*args):
    ok, out, why = cli(*args)
    if not ok:
        return None, why
    try:
        return json.loads(out), ""
    except ValueError:
        return None, f"gh output not JSON: {out.strip()[:80]!r}"

def _site(out, key, base):
    url = base + "/" if key in ("W-SITE-UG", "W-SITE-SYNTHEX") else base
    stripe = {"W-SITE-GROW": "W-STRIPE-GROW-LINKS", "W-SITE-CARDS": "W-STRIPE-CARD-LINKS"}.get(key)
    s, body = get(url)
    if s == 0:
        out[key] = (UNKNOWN, f"{url} could not be checked: {body}")
    elif not 200 <= s < 300:
        out[key] = (FAIL, f"{url} returned HTTP {s}")
    else:
        out[key] = (OK, "")
        if stripe:
            ok = "buy.stripe.com" in body
            msg = f"{url} (HTTP {s}) has no live Stripe buy link" + (" yet (STRIPE_PAYMENT_LINK_* not set)" if key == "W-SITE-GROW" else "")
            out[stripe] = (OK, "") if ok else (FAIL, msg)
        return
    if stripe:   # an unread page proves nothing about its buy links: never leave a stale OK standing
        out[stripe] = (UNKNOWN, f"{url} could not be read, so its Stripe buy links are unknown: {out[key][1]}")

def _failing_checks(rollup):
    """(names of failed checks, reason). reason != "" means the rollup was malformed and nothing may be concluded."""
    if rollup is None:
        return [], ""
    if not isinstance(rollup, list) or not all(isinstance(c, dict) for c in rollup):
        return [], f"statusCheckRollup is not a list of objects: {str(rollup)[:80]}"
    bad = []
    for c in rollup:
        # gh tags each entry with its type. A check run has name + conclusion (None while in
        # progress); a commit status (Vercel, CodeRabbit, nexus/release-receipt) has context + state.
        # The type decides which fields are read (review r5: an untyped row carrying both a failing
        # state and a passing conclusion read as a pass). Anything else proves nothing.
        # Review r6: a COMPLETED run must carry a final conclusion (a null one proves nothing), a
        # running one must carry none, and a row holding the other type's fields is unreadable.
        kind = c.get("__typename")
        if (kind == "CheckRun" and isinstance(c.get("name"), str) and "context" not in c and "state" not in c
                and ((c.get("status") == "COMPLETED" and c.get("conclusion") in CHECK_FINAL)
                     or (c.get("status") in CHECK_RUNNING and c.get("conclusion") in (None, "")))):
            if c["conclusion"] in CHECK_FAILED:
                bad.append(c["name"])
        elif (kind == "StatusContext" and isinstance(c.get("context"), str) and c.get("state") in STATUS_STATES
                and not {"name", "conclusion", "status"} & set(c)):
            if c["state"] in STATUS_FAILED:
                bad.append(c["context"])
        else:
            return [], f"statusCheckRollup entry not a readable check: {str(c)[:80]}"
    return bad, ""

def _all_passed(rollup):
    """True only when every check in a validated rollup positively passed. Call only after _failing_checks read it.
    Review r12: STALE (a run GitHub gave up on) is final but proves nothing; so is anything still running.
    OK needs a pass on every check, not merely the absence of a failure."""
    return all(c.get("status") == "COMPLETED" and c.get("conclusion") in CHECK_PASSED if c.get("__typename") == "CheckRun"
               else c.get("state") in STATUS_PASSED for c in rollup)

def _repo(out, repo):
    short = repo.split("/")[-1]
    prs, why = cli_json("pr", "list", "--repo", repo, "--state", "open", "--limit", str(PR_LIMIT),
                        "--json", "number,headRefOid")
    if not isinstance(prs, list):
        out[f"W-PR-LIST-{short}"] = (UNKNOWN, f"{repo} open PR list could not be fetched: {why or 'unexpected output'}")
        return
    out[f"W-PR-LIST-{short}"] = (OK, "")
    live, complete = set(), True
    if len(prs) >= PR_LIMIT:   # a full page may hide more open PRs: never proof that a missing one closed
        complete = False
        out[f"W-PR-LIST-{short}"] = (UNKNOWN, f"{repo} open PR list hit the {PR_LIMIT} limit; closed-PR sweep skipped")
    for pr in prs:
        n = pr.get("number") if isinstance(pr, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or n < 1 or f"W-PR-{short}-{n}" in live:
            complete = False   # a partial read must never close rows: no sweep below
            out[f"W-PR-LIST-{short}"] = (UNKNOWN, f"{repo} PR list entry unparsable: {str(pr)[:80]}")
            continue
        jid = f"W-PR-{short}-{n}"
        live.add(jid)
        sha = str(pr.get("headRefOid") or "")[:8]
        d, why = cli_json("pr", "view", str(n), "--repo", repo, "--json", "state,statusCheckRollup")
        if not isinstance(d, dict) or "statusCheckRollup" not in d:
            out[jid] = (UNKNOWN, f"{repo}#{n} ({sha}) checks could not be read: {why or 'unexpected output'}")
            continue
        bad, why = _failing_checks(d["statusCheckRollup"])
        if why:
            out[jid] = (UNKNOWN, f"{repo}#{n} ({sha}) checks could not be read: {why}")
            continue
        if not bad and (not d["statusCheckRollup"] or not _all_passed(d["statusCheckRollup"])):
            continue   # review r10/r11/r12: no checks yet, unfinished or stale ones prove nothing: the row (an open FAIL included) is left as it is
        out[jid] = (FAIL, f"{repo}#{n} ({sha}) open with failing checks: {', '.join(map(str, bad[:5]))}") if bad else (OK, "")
    if complete:   # only a fully parsed list proves a missing PR is closed
        out[CLOSED + f"W-PR-{short}-"] = (OK, live)  # rows under this prefix that are not in `live` are closed PRs

def checks():
    """{row id: (state, message)}. A row absent from the result is left alone this run.
    Each check family (one site, one repo) is isolated: an unexpected exception makes that family UNKNOWN, never aborts the run."""
    out = {}
    for key, base in (("W-SITE-UG", UG), ("W-SITE-GROW", UG + "/grow"), ("W-SITE-CARDS", UG + "/cards"), ("W-SITE-SYNTHEX", SX)):
        try:
            _site(out, key, base)
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            for k in (key, {"W-SITE-GROW": "W-STRIPE-GROW-LINKS", "W-SITE-CARDS": "W-STRIPE-CARD-LINKS"}.get(key)):
                if k:
                    out[k] = (UNKNOWN, f"{base} check raised unexpectedly: {reason}")
    for repo in REPOS:
        short = repo.split("/")[-1]
        try:
            _repo(out, repo)
        except Exception as e:
            out.pop(CLOSED + f"W-PR-{short}-", None)   # a partial read must never close rows
            out[f"W-PR-LIST-{short}"] = (UNKNOWN, f"{repo} PR checks raised unexpectedly: {type(e).__name__}: {e}")
    return out

def load_lkg():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}

def apply(d, results, lkg):
    changed = False
    now = datetime.datetime.now().astimezone()
    jobs = {j["id"]: j for j in d["jobs"]}
    expanded = {}
    for jid, (state, msg) in results.items():
        if jid.startswith(CLOSED):
            pre = jid[len(CLOSED):]
            for k, j in jobs.items():
                if k.startswith(pre) and k not in msg and j.get("status") != "done":
                    expanded[k] = (OK, "")
        else:
            expanded[jid] = (state, msg)
    for jid, (state, msg) in expanded.items():
        j = jobs.get(jid)
        if state == OK:
            lkg[jid] = NOW
            if j is not None and (j["status"] != "done" or j.get("check_state") not in (None, OK) or j.get("unknown_since")):
                j.update({"status": "done", "updated": NOW, "blocker": "", "check_state": OK, "last_known_good_at": NOW, "unknown_since": None})
                changed = True
        elif state == FAIL:
            new = {"title": f"ALERT: {msg}", "updated": NOW, "status": "open", "blocker": msg, "check_state": FAIL,
                   "priority": "P1", "unknown_since": None, "last_known_good_at": lkg.get(jid)}
            if j is None:
                d["jobs"].append({"id": jid, "owner": "Guardian watcher", "created": NOW, **new}); changed = True
            elif j["status"] == "done" or j.get("blocker") != msg or j.get("check_state") != FAIL:
                j.update(new); changed = True
        else:  # UNKNOWN
            if j is not None and j["status"] != "done" and j.get("check_state") == FAIL:
                if not j.get("unknown_since"):
                    j["unknown_since"] = NOW; changed = True   # the FAIL row stays exactly as it was
                continue
            was_unknown = j is not None and j["status"] != "done" and j.get("check_state") == UNKNOWN
            since = (j.get("unknown_since") if was_unknown else None) or NOW
            try:
                old = now - datetime.datetime.strptime(since, TS) >= ESCALATE_AFTER
            except ValueError:
                old = False
            text = f"check could not run: {msg} (unknown since {since})" if old else f"check inconclusive since {since}: {msg}"
            new = {"title": f"ALERT: {text}", "updated": NOW, "status": "open", "blocker": text, "check_state": UNKNOWN,
                   "priority": "P1" if old else "P3", "unknown_since": since, "last_known_good_at": lkg.get(jid)}
            if j is None:
                d["jobs"].append({"id": jid, "owner": "Guardian watcher", "created": NOW, **new})
            else:
                j.update(new)
            changed = True
    if changed:
        d["updated"] = NOW
    return changed

def main():
    results = checks()      # network first, outside the jobs.json lock
    lkg = load_lkg()
    jobs_lock.update_jobs(os.path.join(OPS, "jobs.json"), lambda d: apply(d, results, lkg))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE))
    with os.fdopen(fd, "w") as f:
        json.dump(lkg, f)
    os.replace(tmp, STATE)
    with open(HEARTBEAT, "w") as f:
        f.write(NOW + "\n")

if __name__ == "__main__":
    main()
