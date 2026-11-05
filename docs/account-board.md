# Account usage board (RA-8190, AR-04)

`scripts/account_board.py` builds the Ops Board's account widget. It reads the account map (`ops/ACCOUNT-MAP.yaml`, AR-01) and the HEADROOM log (AR-02) and prints one row per account, plus alerts.

It only reads. It never signs in or out, switches accounts, reads a credential or decides to spend. Emails are compared in memory and never printed. Every printed value is a checked id, a number or a fixed string, never text from the log.

## Columns

| Column | Source | When there is no source |
|---|---|---|
| `label`, `provider`, `plan`, `machines` | account map | (map is required) |
| `state` | HEADROOM: the event still holding the account (`5h_cooling`, `weekly_cooling`, `auth_expired`, `billing_blocked`, `on_demand_capped`), else `green` | `green` with the log present but empty |
| `last_event` | latest HEADROOM event for the account: event, time in AEST, machine | `null` |
| `reset_at`, `reset_source` | when the hold ends, in AEST. `printed` = the CLI printed it; `fallback` = the picker's fallback hold (5 h, 24 h, or 12 h for a person-needed event) | `null` when not held |
| `active_jobs`, `queued_jobs` | `--jobs` table: `{"mini": {"active": 1, "queued": 3}}` | `null`, never 0 |
| `job_hours_7d` | `--job-hours` table: `{"mini": 31.5}` | `null`, never 0 |
| `usage_pct` | `--usage` table: `{"claude-mini": 64}` (percent of the account's known window) | `null` |

An account pinned to more than one machine shows the sum, and only when every one of its machines is in the table.

State and reset use the same hold rules as the night-queue picker (`docs/account-picker.md`); the code is shared, not copied.

## Alerts

| Alert | Fires when |
|---|---|
| `mis_pin` | a machine has no Claude account, or two or more accounts for one provider |
| `shared_claude_email` | one Claude email is pinned on two or more machines (across accounts, or one account listing two machines). Only labels and machine ids are printed |
| `high_usage` | an account's `usage_pct` is over 80 |

`checks` gives each one as `ok`, `alert` or `UNKNOWN`. HEADROOM records limit hits, not percentages, so `high_usage` is `UNKNOWN` until a usage table covers every account. No usage source exists yet; neither does a jobs or job-hours source.

## Exit codes (the alert hook)

| Code | Meaning |
|---|---|
| 0 | board printed, no alerts |
| 1 | board printed, one or more alerts |
| 2 | map, a table or arguments unusable (missing map, repeated key, malformed label) |
| 3 | HEADROOM log unreadable or its folder missing (ops SSD not mounted): UNKNOWN, no board |

A cron or lane runner can call it and raise an alert on exit 1, or a failure on 2 or 3.

## Use

```bash
python3 scripts/account_board.py                       # JSON
python3 scripts/account_board.py --format md           # table for the Ops Board
python3 scripts/account_board.py --job-hours ./job-hours.json --usage ./usage.json
```

`--log` defaults to `$HEADROOM_LOG`, else the AR-02 default on the Mini ops SSD. `--map` defaults to `ops/ACCOUNT-MAP.yaml`, which lands with RA-8187; until then the board exits 2.

## Not done in this change

- Showing it in the Mission Control dashboard. The dashboard runs on Vercel and cannot read the Mini's ops SSD, so a page there would show nothing live. Wiring needs the Mini to publish the JSON somewhere the dashboard can read; that is a separate change.
- Sources for jobs, job-hours and usage percent.
