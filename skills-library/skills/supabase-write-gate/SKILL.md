---
name: supabase-write-gate
description: Fail-closed PreToolUse gate on Supabase MCP writes. Read tools stay open; every write is denied unless a founder break-glass file names the project. Fires automatically on any mcp__*Supabase* call — you do not invoke it. Read this when a Supabase write is blocked, when adding a machine to the fleet, when a new Supabase read tool needs allowlisting, or when deciding how a schema change should reach production.
version: 1
updated: 2026-07-29
---

# supabase-write-gate — the door the sequence didn't cover

## Why it exists

2026-07-28 02:54 UTC. An agent created `ClientPasswordResetToken` in RestoreAssist
**production** through `apply_migration`. No branch, no PR, no independent review, no
release receipt — and **no code artifact on any machine**. The MacBook, the Mac Mini,
and both the Codex and Claude session corpora were searched with passing positive
controls. Nothing. The table stored reset tokens verbatim with no unique constraint.

Nobody violated the sequence. `settings.json` proved why: `Bash` fires
`pr_release_gate.py`; `mcp__claude_ai_Supabase__apply_migration` fired **nothing**. The
estate's entire review chain hangs off Bash and git, and an MCP call is neither.

"Green tests grant authority to commit" cannot apply here either — `apply_migration`
produces no diff, no SHA and no test that could go red. There is nothing for evidence
to bind to.

Ten `ACTIVE_HEALTHY` projects were reachable this way, including RestoreAssist prod,
Unite-Group, ATO and ITR-Dimitri.

## How it decides

**Positive proof, not detection.** It does not hunt for dangerous tools — it permits a
named set of read tools and denies everything else. A write tool Supabase ships next
month is denied on arrival because it is absent from the allowlist, not because someone
predicted its name. Verified: a fabricated `obliterate_everything` is blocked.

`execute_sql` is the one read-and-write tool, so it must prove itself: the statement
has to parse as a read AND contain no mutating or privileged construct anywhere.
`SELECT 1; DROP TABLE "Foo";` is blocked. So is a `WITH … DELETE … RETURNING` CTE.
Unparseable is denied, never allowed.

Every decision is appended to `~/.claude/logs/supabase-write-gate.jsonl`.

## Break-glass

`~/.claude/.supabase-write-approved.json`:

```json
{"project_id": "<ref>", "expires_at": <unix seconds>, "reason": "..."}
```

A file, not an environment variable, because an env var is trivially set by the agent
it is meant to restrain. It must name the exact project and be unexpired; a malformed
grant is no grant. Every use is logged as `PERMIT_BREAK_GLASS`.

**An agent creating this file is a violation, not a workaround.** It is a path the
founder writes by hand.

## Where schema change goes instead

A Prisma migration, on a branch, in a PR, with an independent review bound to the exact
SHA and a `PR_RELEASE_GATE_PASS` receipt. That path leaves an artifact; this one did
not, which is why the 2026-07-28 change took four hours and three machines to
reconstruct and still yielded no author.

Do not reach for Supabase database branches as the alternative without checking them
first: on 2026-07-29 two of Unite-Group's three branches (`e2e-gate`,
`pilot-v1-scratch`) had been sitting in `MIGRATIONS_FAILED` for five weeks unnoticed.
The mandated branch-first validation was not running.

## Installing on a machine

```bash
python3 ~/.claude/skills/supabase-write-gate/scripts/install_supabase_write_gate.py
```

Idempotent, backs up `settings.json`, validates the JSON before writing. `bootstrap.sh`
calls it, so a fresh machine is covered without anyone remembering — `hooks/` and
`settings.json` are gitignored and do **not** sync with this repo. Installed and
proven on the MacBook and the Mac Mini, 19/19 controls each.

## Adding a read tool

Add the bare name to `READ_TOOLS` in `hooks/PreToolUse/supabase_write_gate.py`, then
re-run `scratchpad/test_supabase_gate.sh`. Never widen it to a prefix or a directory —
that is how the route-safety scanner nearly grew a permanent blind spot the same day.

## Proving it works

`test_supabase_gate.sh` covers 19 cases: eleven must-block including default-deny and a
malformed payload, eight must-permit including reads, a read-only CTE, and
non-Supabase tools passing through untouched. **Run the permits as well as the blocks.**
A gate that only ever blocks is an outage, and this estate has already shipped one
reviewer that returned 545 NO and 0 PASS.

Related: [[agent-wrote-prod-schema-via-mcp]] · [[enforcement-wiring-contract]] ·
[[heuristic-boundary-loses-to-adversarial-review]] · [[proof-discipline]]
