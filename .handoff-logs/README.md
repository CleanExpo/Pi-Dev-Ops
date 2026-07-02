# .handoff-logs/

Timestamped healthcheck logs from `scripts/handoff-loop.sh` (`handoff-<ts>.log`), one per
`/session-handoff` or `/resume-from-handoff` gate run. Each records PASS/FAIL/SKIP per gate
and the final READY/BLOCKED verdict.

The `*.log` files are gitignored (local runtime artifacts). This README keeps the directory
tracked so the path always exists.
