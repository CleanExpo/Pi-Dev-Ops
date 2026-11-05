# HEADROOM events (RA-8188, AR-02)

When a night-lane job stops on an account limit, the CLI prints one known line. `scripts/headroom_events.py` reads the end of that job's output and appends one JSON line per event to the HEADROOM log. The night-queue picker (AR-03) reads that log to skip a cooling account.

It records what the CLI said. It never signs in, out or switches accounts, and it never decides to spend.

## Events

| Event | Meaning | Seen as |
|---|---|---|
| `5h_cooling` | short usage window used up; waits for the printed reset | Claude `5-hour limit reached ∙ resets 3:30pm`, `Claude usage limit reached`, `You've hit your usage limit · resets 11am` |
| `weekly_cooling` | weekly allowance used up | Claude `You've hit your weekly limit · resets Oct 9 at 1am` |
| `auth_expired` | the login is dead; a person must sign in again | Claude `Login expired · Please run /login`, `OAuth session expired`; Codex `Your workspace is out of credits` (an expired Codex token, not billing) |
| `billing_blocked` | the plan itself blocks use; a decision for Phill | Cursor `Get Cursor Pro for more Agent usage`; Claude `organization has disabled Claude subscription access` |
| `on_demand_capped` | included usage gone; more needs a spend limit (paid overflow, Phill's GO only) | Cursor `set a Spend Limit to continue with this model` |

Codex usage-limit lines have no live sample on the Mini yet, so their events carry `"source": "unverified"`.

## Record

```json
{"schema": "headroom/1", "ts": "2026-11-05T03:40:00+00:00", "machine": "mini", "provider": "claude",
 "event": "weekly_cooling", "pattern_id": "claude.quota", "source": "observed",
 "reset_at": "2026-10-08T15:00:00+00:00", "exit_code": 1, "job": "RA-8188"}
```

Every value is built by the script. The CLI's own words are never stored. `reset_at` is `null` when the line prints no readable reset; it is never a guess. There is no account email: AR-03 joins `machine` + `provider` to `ops/ACCOUNT-MAP.yaml`.

Known gaps: `reset_at` is `null` for `resets Thu 9am` and for Codex `try again at ...` lines (the shared reader in `mesh/quota.py` reads `resets <time>` and `resets <Mon> <day> at <time>`), so the picker needs its own fallback hold. Codex output is read even on exit 0 (`codex exec` exits 0 on its limit), so a Codex report line that starts with a limit message would count; those events are marked `unverified`.

## Where it writes

`$HEADROOM_LOG`, else `/Volumes/Mini Mini 2T Storage/ops/headroom/headroom-events.jsonl` (a design default). The path must be absolute. The script creates only the last folder (`headroom/`), and gives up on a lock held longer than 5 seconds rather than stall the job. If the ops SSD is not mounted it exits 3 and writes nothing, so a missing log never looks like a quiet night.

## Wiring a wrapper

After the agent exits in `run.sh` (for example `~/agent-work/lib/run-template.sh`, right after `wait "$CPID"`):

```bash
RC=$?
bash "$HOME/Pi-Dev-Ops/scripts/headroom_scan_job.sh" "$J" claude "$RC" "$J/claude.out"
```

The helper always exits 0 and writes its result, or `headroom: FAILED ...`, to `<job>/job.log`. On a machine without the ops SSD (the MacBook), set `HEADROOM_LOG` to a local path first.

## Check by hand

```bash
python3 scripts/headroom_events.py scan tests/fixtures/headroom/planted_marker.txt \
  --provider claude --machine mini --exit-code 1 --log ./headroom-check.jsonl
```
