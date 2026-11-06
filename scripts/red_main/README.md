# Red-main auto-owner (RA-8174)

Any CleanExpo repo whose default branch goes red gets one owner and one fix lane
within one watcher cycle, and the jobs parked behind it resume when it is green.

## What it does each cycle (every 5 min on the Mini)

1. **Detect.** For every non-archived CleanExpo repo pushed in the last 60 days, read
   the last 100 workflow runs on the default branch. Red = the latest *completed*
   run of any active workflow failed. Scheduled jobs count (the Unite-Group Nexus
   Heartbeat failed daily for 11 days and nothing owned it). PR runs and runs still
   in progress do not. A failed `gh` read is UNKNOWN: it never closes a card and
   never resumes a job.
2. **Board.** One card per repo, `W-MAIN-RED-<repo>`, in `ops/jobs.json`, written
   under the same `<jobs.json>.lock` every other board writer takes.
3. **Lane.** A red card with no lane gets one on the least-busy host (fewest running
   `claude -p` sessions) among hosts that carry `~/agent-work/lib/run-template.sh`
   (Mini, MacBook). At most `RED_MAIN_MAX_NEW_LANES` (2) new lanes per cycle,
   newest red first. A single-run lock means two cycles never both start one.
4. **Fix pushed, no PR.** The lane works on `fix/red-main-<episode>`. If that branch
   is on GitHub with no PR for 10+ minutes: a live lane is flagged on the card; an
   ended lane is relaunched with a PR-only brief. Launch cap: 2 per red episode,
   then the card goes unowned and escalates.
5. **Review path.** The lane brief says: if CodeRabbit is rate-limited, take the
   Codex review lane and the legitimate `nexus/release-receipt` path. The watcher
   itself never opens a PR or posts a status.
6. **Parked jobs.** `red_main_watch.py park <JOB-ID> <Org/Repo>` sets
   `waits_for_main`; the first green read of that repo puts the job back to the
   status it parked from.
7. **Owner + age.** `annotate` adds `[owner: X; age: Nm]` to every AMBER/RED line
   (fleet watcher facts and this watcher's own lines). A line unowned for 30+
   minutes becomes an open `W-WATCH-<key>` card on the board; it closes when the
   line goes away. A red-main card unowned 30+ minutes is raised to P0 with an
   `UNOWNED` blocker.

## Install (after the PR merges)

Mini (board host):

```bash
cp scripts/launchagents/com.unite.red-main-watch.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/com.unite.red-main-watch.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.unite.red-main-watch.plist
tail -f ~/Library/Logs/red-main-watch.log
```

The plist runs the copy in pdo-runtime, which the mesh runner keeps on
`origin/main`, so later merges deploy themselves.

MacBook fleet watcher (`~/session-handoffs/watch/fleet_watch.sh`), just before the
Haiku verdict step, so every AMBER/RED line carries owner and age:

```zsh
say "# END FACTS"   # marks a complete read; only a complete read may close W-WATCH cards
RM="python3 '/Volumes/Storage Unit/Application-Data/nexus-mesh/pdo-runtime/scripts/red_main_watch.py' annotate"
if ssh -o ConnectTimeout=8 -o BatchMode=yes mini "$RM" < $F > $F.annotated 2>/dev/null && [[ -s $F.annotated ]]; then
  mv $F.annotated $F
else
  rm -f $F.annotated; say "AMBER red-main annotate could not run on the Mini; owner/age missing this cycle."
fi
```

## Switches

| Env | Default | Meaning |
|---|---|---|
| `RED_MAIN_LAUNCH` | `0` | `1` lets scan start lanes (the plist sets it). |
| `RED_MAIN_HOSTS` | `mini=local,macbook=macbook` | Lane hosts, in tie-break order. |
| `RED_MAIN_MAX_NEW_LANES` | `2` | New lanes per cycle. |
| `RED_MAIN_MAX_LAUNCHES` | `2` | Lanes per red episode before it goes unowned. |
| `RED_MAIN_PR_GRACE_MIN` | `10` | Pushed fix with no PR this long is overdue. |
| `RED_MAIN_ESCALATE_MIN` | `30` | Unowned this long goes to the board. |
| `RED_MAIN_ACTIVE_DAYS` | `60` | Repos pushed within this window are scanned. |
| `RED_MAIN_REPOS` | (all) | `Org/A@main,Org/B` pins the repo list. |
