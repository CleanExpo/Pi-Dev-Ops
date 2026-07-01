# docs/session-handoffs/

Durable output of `/session-handoff` (the "1" of the handoff combo). Each run writes
`handoff-<YYYYMMDD-HHMMSS>.md` here after `scripts/handoff-loop.sh` gates the tree green.
`/resume-from-handoff` (the "2") loads the latest report from this directory when invoked
with no argument.

The generated `handoff-*.md` files are gitignored (per-session local artifacts). This README
and the directory are tracked so the path always exists.
