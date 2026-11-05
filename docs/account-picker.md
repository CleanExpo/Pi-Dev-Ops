# Night-queue picker (RA-8189, AR-03)

`scripts/account_picker.py` answers one question for a night lane: which machine should run the next job? It reads the account map (`ops/ACCOUNT-MAP.yaml`, AR-01) and the HEADROOM log (AR-02) and prints a JSON decision.

It only chooses. It never claims a job, signs in or out, switches accounts, reads a credential or decides to spend. It never prints an email, and every reason it prints is a fixed string.

## Rules

| Step | Rule |
|---|---|
| Pin | A machine needs exactly one account for the provider in the map. None or two: skipped. |
| Skip | A machine is skipped while a HEADROOM event holds it: `5h_cooling`, `weekly_cooling`, `auth_expired`, `billing_blocked`, and `on_demand_capped` (paid overflow needs Phill's GO). |
| Hold ends | `5h_cooling` and `weekly_cooling` hold until the printed `reset_at` (if it is within 8 days). With no reset: 5 hours, 24 hours. `auth_expired`, `billing_blocked`, `on_demand_capped` need a person and are retried at most once per 12 hours. The longest hold wins. |
| Prefer | Max seat first, then "green" (no limit event in 7 days) before "recovered", then fewest job-hours (a machine missing from the job-hours table is unknown, shown as `null`, and ranks after machines with known hours), then longest since its last limit event. |
| Evenness | Each Max seat within ±20% of the Max seats' mean job-hours. With no job-hours table, or one missing a Max seat, evenness is `UNKNOWN`, never even. The ±20% check uses the exact deviation; only the printed `spread` is rounded. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | picked a machine (`"pick"`) |
| 1 | nothing eligible (every candidate skipped) |
| 2 | map, job-hours table or arguments unusable (including a repeated key in the map, or job-hours too large to add up) |
| 3 | HEADROOM log unreadable, its folder is missing (ops SSD not mounted), or it is a link whose target is missing: UNKNOWN, no pick |

A mounted log folder with no file yet is a real "no events" and prints `"log": {"status": "absent"}`. Lines that are not valid `headroom/1` records are counted in `"malformed"` and never trusted. Leaving out `--machines` means every mapped machine. An empty value (`--machines ""`) means no machines, so nothing is picked (exit 1). In Python, `candidates=None` means every machine and `candidates=[]` means none. A folder the picker may not open is UNKNOWN (exit 3), like a missing one. The map may use YAML anchors and `<<:` merge keys; a key written twice is refused.

## Use

```bash
python3 scripts/account_picker.py --provider claude --machines mini,macbook \
  --job-hours ./job-hours.json      # optional: {"mini": 31.5, "macbook": 22}
```

`--log` defaults to `$HEADROOM_LOG`, else the AR-02 default on the Mini ops SSD. `--map` defaults to `ops/ACCOUNT-MAP.yaml` (lands with RA-8187).

## Wiring a lane runner (not done in this change)

The night-lane runner lives outside this repo (`~/agent-work/night-lane.sh`). Before it launches an item on a machine, it can ask the picker and only launch when this machine is the pick, or skip the slot when the exit code is 1 or 3. Wiring is a separate change so a running lane is never edited mid-night. No job-hours source exists yet; until one does, the picker reports evenness as `UNKNOWN`.
