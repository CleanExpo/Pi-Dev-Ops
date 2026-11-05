# Codex review failover, Mini to MacBook (RA-8191, AR-05)

`scripts/codex_failover.py review` runs one Codex review brief on the Mini. If the Mini's Codex login is dead, it writes a HEADROOM `auth_expired` event and runs the same brief on the MacBook, against the same commit. It only detects. It never signs in or out.

## Five whys

| Why | Answer | Tests |
|---|---|---|
| W1. Why detect a dead login apart from other failures? | A dead login needs a person; quota waits out a reset; a bad brief needs a fix. Treating them the same either holds a healthy machine or re-runs a broken review. | `test_detect_*` |
| W2. Why run the review on the MacBook? | Every PR needs an independent review before push. When the Mini login dies at night, the queue stalls until Phill wakes. The MacBook has its own ChatGPT login, so the review can still happen. | `test_failover_mini_401_*`, `test_failover_missing_auth_file_*` |
| W3. Why write HEADROOM `auth_expired`? | The picker (AR-03) reads HEADROOM. Without the event, it keeps sending Codex work to the Mini, and each job fails the same way. | `test_failover_*` rows checks |
| W4. Why bind the MacBook review to the same commit? | A review of a different commit proves nothing about the one being pushed. The receipt must name one HEAD. | `test_failover_head_mismatch_is_unavailable` |
| W5. Why never sign in or out? | Founder rule: re-auth is human-only, and swapping logins to stack quotas is not compliant. Automation that can sign in can also sign in to the wrong account. | `test_login_*` |

Root need: reviews keep flowing overnight on the subscriptions Phill already pays for, without anyone touching a login.

## How it decides

1. `auth.json` in `$CODEX_HOME` (else `~/.codex`) is missing, unreadable, or not ChatGPT plan auth: the Mini is down (`codex.auth_file`). Codex is not run. Only `auth_mode` and whether an API key field is set are read, never a token.
2. Otherwise Codex runs the brief (`codex exec --sandbox workspace-write --output-last-message <out>.last.md -`).
3. A run that wrote a final message authenticated, whatever its transcript quotes.
4. With no final message, a line that starts with a HEADROOM auth string is a dead login: `unexpected status 401 Unauthorized` (seen live on the Mini with no login, 5 Nov 2026) or `workspace is out of credits`.
5. Anything else, including quota, is a plain failure: exit 1, no failover, no event.

## The MacBook run

- ssh alias `macbook` (`CODEX_FAILOVER_HOST` overrides), `BatchMode=yes`, so a missing key fails instead of prompting.
- The commit travels as `git bundle create - HEAD` into a new folder, `~/agent-work/codex-failover/<ticket>-<sha12>-<epoch>`. The MacBook's own `~/Pi-Dev-Ops` is never touched.
- The folder's `HEAD` must equal the Mini's before Codex runs. A mismatch is exit 4.
- The transcript goes to `--out` and the final message to `<out>.last.md`, the same files as a Mini run.
- If the MacBook login is dead too, a second `auth_expired` event is written for `macbook` and the exit is 5.

## Exit codes

| Code | `review` | `detect` |
|---|---|---|
| 0 | review ran (`lane` says where) | ok |
| 1 | review ran and failed for a non-auth reason | failed |
| 2 | bad arguments, brief missing, or repo HEAD unreadable | |
| 3 | | auth_failed |
| 4 | Mini down; MacBook unreachable, bundle failed, or HEAD mismatch | |
| 5 | Mini and MacBook both down | |

A HEADROOM write failure (ops SSD not mounted) is reported in `headroom` in the JSON summary and does not stop the failover.

## Use

```bash
python3 scripts/codex_failover.py review --brief brief.md --out review.txt --job RA-8191
python3 scripts/codex_failover.py detect --transcript review.txt --last-message review.txt.last.md
```

## Not wired yet

The release gate's Codex lane (`lane_codex` in `~/.claude/skills/pr-release-gate/scripts/independent_review.py`) is outside this repo and is not changed here. Owner: the pr-release-gate maintainer. Step: when `lane_codex` returns no valid report, call `codex_failover.py detect` on its transcript, and on exit 3 run `review` with the same brief.

## Known gaps

- Only the two auth strings above are matched. Any other auth error text (for example a malformed `auth.json` printing `plan type is required`) reads as a plain failure, so the Mini is not held by mistake, and there is no failover for it.
- A token that is expired but still in `auth.json` is caught only by the run's own output (step 4).
