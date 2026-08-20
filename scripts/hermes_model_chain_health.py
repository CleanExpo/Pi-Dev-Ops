#!/usr/bin/env python3
"""Probe every Hermes profile's model chain against the live provider.

Why this exists
---------------
As of 2026-08-20 every profile's PRIMARY is an OpenRouter `:free` model. Free
tiers in this estate are demonstrably volatile: on 2026-08-19, `z-ai/glm-5.2:free`
returned HTTP 429 on 3/3 attempts and `qwen/qwen3-next-80b-a3b-instruct:free`
returned 404 because its free tier had been withdrawn entirely. A model that
disappears does not announce itself — the gateway starts fine and fails per turn,
which is exactly how Hermes sat broken for six days in August.

`hermes doctor` validates config SHAPE. It does not call the models. This does.

Per-profile status
------------------
  OK          at least one entry was probed and answered
  DOWN        EVERY entry was probed and every one failed — that profile cannot serve
  DEGRADED    a probed entry failed, but an unprobeable fallback remains. The
              profile may still serve, so "cannot serve" is not claimed — but a
              failed primary needs attention, so it still alarms.
  UNVERIFIED  nothing in the chain could be probed, so health is UNKNOWN, not good
              (e.g. `ownest`, whose chain is moa + openai-codex, neither reachable
              over HTTP). Reported loudly, but does not alarm, because it is a
              standing property of that profile rather than a new fault.

Each state says exactly what was PROVEN and no more. DOWN and DEGRADED are kept
apart because both Windows profiles are free + free + openai-codex: if the free
tier goes down, the codex fallback may well serve them, and reporting a proven
outage there would be a claim beyond the evidence.

Exit codes
----------
  0  nothing failed a probe and the run completed within its budget
  1  at least one profile is DOWN or DEGRADED, OR the run exceeded RUN_BUDGET_S
     (an incomplete run is a fault: entries were never attempted, so a clean
     exit would be a timeout dressed as a pass)
  2  could not run — no API key, or a profile config that cannot be read/parsed

Usage
-----
  python3 scripts/hermes_model_chain_health.py
  python3 scripts/hermes_model_chain_health.py --json
  python3 scripts/hermes_model_chain_health.py --inject-broken   # self-test

Needs PyYAML, so it must run under an interpreter that has it. /usr/bin/python3
does NOT; /opt/homebrew/bin/python3 does. The scheduled plist pins the latter
deliberately: the Hermes venv also has PyYAML but lives on /Volumes/Storage Unit,
and a monitor that dies whenever the external drive unmounts cannot report that
the external drive unmounted.

`--inject-broken` adds a deliberately non-existent model as a fake profile's only
entry and asserts the script reports failure. Run it after changing this file: a
health check that cannot fail is not a health check.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERMES = os.path.expanduser("~/.hermes")
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

# Per-probe timeout. Measured latencies for these models are 0.3-2.0s, so 30s is
# already ~15x headroom; the previous 90s bought nothing. It matters because the
# worst case is multiplicative: 6 profiles x up to 3 entries, so 90s per probe put
# the ceiling near 27 minutes of a hung run holding the daily slot.
PROBE_TIMEOUT_S = 30
# Hard wall-clock ceiling for the whole run. Past this, remaining entries are
# reported as unprobed rather than the run hanging indefinitely — launchd has no
# way to know the difference between "slow" and "wedged".
RUN_BUDGET_S = 300


def read_key() -> str | None:
    try:
        for line in open(os.path.join(HERMES, ".env"), errors="ignore"):
            m = re.match(r'\s*OPENROUTER_API_KEY\s*=\s*["\']?([^"\'\s]+)', line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return None


class ConfigError(RuntimeError):
    """A profile config could not be read or parsed.

    Deliberately fatal. An earlier revision turned this into a fake chain entry
    ("UNREADABLE"), which probe() then reported as unprobeable, so the profile
    came out UNVERIFIED and the run exited 0 — a corrupt config read as "checked,
    nothing wrong". That is the failed-read-as-success pattern this tool exists
    to catch, reproduced inside the tool.
    """


def profiles() -> dict[str, list[tuple[str, str]]]:
    """profile name -> ordered [(provider, model)] chain, primary first."""
    import yaml

    out: dict[str, list[tuple[str, str]]] = {}
    paths = [(os.path.join(HERMES, "config.yaml"), "default")]
    for p in sorted(glob.glob(os.path.join(HERMES, "profiles", "*", "config.yaml"))):
        paths.append((p, os.path.basename(os.path.dirname(p))))
    for path, name in paths:
        try:
            cfg = yaml.safe_load(open(path)) or {}
        except Exception as exc:  # noqa: BLE001 - surfaced as ConfigError below
            raise ConfigError(f"{path}: {exc}") from exc
        model = cfg.get("model") or {}
        chain = [(model.get("provider", "?"), model.get("default", "?"))]
        for fb in cfg.get("fallback_providers") or []:
            chain.append((fb.get("provider", "?"), fb.get("model", "?")))
        out[name] = chain
    return out


def probe(provider: str, model: str, key: str) -> tuple[bool | None, str]:
    """Return (ok, detail). ok is True/False, or None when the entry cannot be probed."""
    if provider != "openrouter":
        # Not probeable over HTTP. `hermes proxy providers` offers only nous and xai,
        # so openai-codex (a ChatGPT OAuth subscription) genuinely cannot be called
        # from here. Report UNKNOWN, never OK — an unprobed entry must not be able to
        # make a profile look verified.
        return None, "UNPROBEABLE (no HTTP endpoint; hermes proxy supports only nous/xai)"
    body = {
        "model": model,
        "max_tokens": 20,
        "reasoning": {"enabled": False},
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
    }
    req = urllib.request.Request(
        OPENROUTER,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S).read())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} {exc.read()[:120].decode(errors='ignore')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    dt = time.time() - t0
    if "error" in d:
        return False, str(d["error"])[:140]
    msg = (d.get("choices") or [{}])[0].get("message") or {}
    text = (msg.get("content") or msg.get("reasoning") or "").strip()
    if not text:
        return False, "empty response"
    cost = (d.get("usage") or {}).get("cost", 0.0)
    return True, f"{dt:.1f}s ${cost:.6f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inject-broken", action="store_true",
                    help="self-test: assert the check reports a dead model")
    args = ap.parse_args()

    key = read_key()
    if not key:
        print("FATAL: no OPENROUTER_API_KEY in ~/.hermes/.env", file=sys.stderr)
        return 2

    try:
        chains = profiles()
    except ConfigError as exc:
        # Exit 2, never 0. A config we cannot read is an unknown we must not
        # dress up as a clean run — launchd would record success.
        print(f"FATAL: unreadable profile config — {exc}", file=sys.stderr)
        return 2
    if args.inject_broken:
        chains = {"__selftest__": [("openrouter", "definitely/not-a-real-model-xyz")]}

    report: dict[str, dict] = {}
    failed_profiles = []
    unverified_profiles = []
    started = time.time()
    budget_exceeded = False
    for name, chain in chains.items():
        entries = []
        any_ok = False
        any_probed = False
        all_probed = True
        for provider, model in chain:
            if time.time() - started > RUN_BUDGET_S:
                budget_exceeded = True
                ok, detail = None, f"NOT PROBED (run exceeded {RUN_BUDGET_S}s budget)"
            else:
                ok, detail = probe(provider, model, key)
            if ok is None:
                all_probed = False
            else:
                any_probed = True
                any_ok = any_ok or ok
            entries.append({"provider": provider, "model": model, "ok": ok, "detail": detail})
        # Four states. Each says exactly what was PROVEN, never more.
        #   OK           something answered
        #   DOWN         every entry was probed and every one failed
        #   DEGRADED     a probed entry failed, but an unprobeable fallback remains,
        #                so "cannot serve" is NOT proven — still alarms, because a
        #                failed primary needs attention either way
        #   UNVERIFIED   nothing could be probed; health is unknown, not good
        if any_ok:
            status = "OK"
        elif not any_probed:
            status = "UNVERIFIED"
        elif all_probed:
            status = "DOWN"
        else:
            status = "DEGRADED"
        report[name] = {"chain": entries, "status": status,
                        "healthy": status == "OK", "verified": any_probed}
        if status in ("DOWN", "DEGRADED"):
            failed_profiles.append(name)
        elif status == "UNVERIFIED":
            unverified_profiles.append(name)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, r in report.items():
            print(f"[{r['status']:<10}] {name}")
            for e in r["chain"]:
                mark = {True: "ok  ", False: "FAIL", None: "????"}[e["ok"]]
                print(f"        {mark}  {e['provider']}/{e['model']}  — {e['detail']}")
        if failed_profiles:
            print(f"\nPROFILES WITH NO WORKING MODEL: {', '.join(failed_profiles)}")
        if unverified_profiles:
            print(f"UNVERIFIED (nothing in the chain could be probed): {', '.join(unverified_profiles)}")
        if budget_exceeded:
            print(f"\nRUN INCOMPLETE — exceeded the {RUN_BUDGET_S}s budget; entries above "
                  "marked NOT PROBED were never attempted. Treat this as a fault, not a pass.")
        if not failed_profiles and not unverified_profiles and not budget_exceeded:
            print("\nEvery profile has at least one model proven to answer.")

    if args.inject_broken:
        ok = bool(failed_profiles)
        print(f"\nSELF-TEST: {'PASSED — the check detects a dead model' if ok else 'FAILED — a dead model was not flagged'}")
        return 0 if ok else 1

    # An incomplete run is a fault. Without this, a systematically hung provider
    # would blow the budget, mark everything NOT PROBED -> UNVERIFIED, and exit 0 —
    # a timeout dressed as a quiet clean run, which is the exact failure class this
    # tool exists to catch.
    return 1 if (failed_profiles or budget_exceeded) else 0


if __name__ == "__main__":
    sys.exit(main())
