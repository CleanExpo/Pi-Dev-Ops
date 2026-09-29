# Mission Control JEV shadow runner

**State:** local synthetic `/control` candidate. The deployed browser suite across the 20 surfaces in WP-02/WP-06 still needs to be built. This runner does not grade a page, authorise GO, merge, or deploy.

## Input and offline replay

For the connected local `/control` browser journey, one command runs Playwright and this offline runner:

```bash
python scripts/mission_control_shadow_check.py
```

The browser test intercepts all Pi-CEO sources with synthetic responses. It checks the project scan state, selection, matched pipeline, API failures and page errors. The wrapper writes a browser snapshot and separate advisory receipt under ignored `dashboard/test-results/mission-control-shadow/`. Both receipts carry `workspace_dirty`, because HEAD alone does not identify uncommitted code and this local check is not deployment proof. A failed browser assertion still writes a snapshot with `failure`; J2 becomes eligible for later triage, but the wrapper keeps the browser's failing exit code. `MISSION_CONTROL_CHROMIUM_PATH` can point to a local Chromium binary when Playwright's normal browser installation is unavailable.

Write one JSON object per line with this allowlisted schema. This sample is synthetic:

```json
{"run_id":"demo-001","sha":"ded1a54e24f547861c89e85c5056e8b77176bb59","surface":"/control","visible_text":"No scan evidence","network_calls":[{"method":"GET","path":"/api/projects/health","status":200}],"assertions":["Project state is visible"],"data_classification":"synthetic"}
```

`failure` (assertion message) and `action` (control label) are optional. J1 is always asked, J2 is added on failure, J3 on an action, and J4 when assertion descriptions are present. Do not put headers, cookies, request bodies, credentials, or customer records in a snapshot. Only the allowlisted fields enter the prepared state; network query strings are removed, and known secret, email and issue ID patterns are masked.

```bash
python scripts/mission_control_jev_shadow.py snapshots.jsonl receipts.jsonl
```

Offline mode is the default. It writes `NOT_EVALUATED` for every question and does not make a network call. Each output line records the run ID, SHA, surface, contract, time, mode, labels and (if available) model/usage, never page text. Invalid input stops the run with an error; do not use a partial receipt file as a completed batch.

## First live synthetic evaluation

The only implemented egress mode accepts records explicitly marked `data_classification: synthetic`:

```bash
python scripts/mission_control_jev_shadow.py snapshots.jsonl receipts.jsonl --live-synthetic --ledger /persistent/mission-control-jev-budget.sqlite
```

The secret store must provide `TYPESAFE_API_KEY` in the runner environment; do not paste a key into a tracked file or terminal transcript. The runner pins `jev-1.13.0` so an alias change cannot silently alter the reviewed contract. The founder's 29 Sept decision in `../nexus-release-harness/adoption.md` is **no daily Jev cap**. Each attempted call is recorded in a persistent SQLite ledger with a conservative 64,000-token reservation; successful responses also record measured input tokens and estimated cost at the currently documented US$0.042 per million input tokens. An operator can reinstate a daily stop with `JEV_DAILY_CAP_USD` or `--daily-cap`; a cap applies only to one ledger, so multiple runners need shared storage for a common stop. Recheck vendor price and limits before live activation. The request times out after 15 seconds; invalid answers or service failure remain `NOT_EVALUATED` with an attempted-call receipt and unknown actual cost. This is advisory triage only.

## Remaining proof before production snapshots

1. Capture real browser receipts with deployed SHA and deterministic pass/fail assertions; keep this runner's advisory file separate from the grade.
2. Independently review data minimisation and redaction against actual snapshots. The current synthetic-only gate deliberately prevents real-data egress.
3. Obtain an accessible TypeSafe runner and scoped key, make a small hand-checked call, then label 60 representative snapshots and report held-out accuracy, abstention, latency and measured tokens before scaling to nightly volume.
4. Provide a durable ledger or central accounting service for multiple machines; verify a shared optional cap under concurrency if enabled.

Focused verification: `python -m pytest tests/test_mission_control_jev_shadow.py -q`. That suite replays 1,000 varied synthetic snapshots offline and tests redaction, malformed input, response validation and optional budget exhaustion without network access. The connected browser check was run in both success and deliberately injected-failure modes; the latter exited nonzero and still produced a J2-ready offline receipt.
