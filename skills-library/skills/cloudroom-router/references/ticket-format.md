# Ticket format

The router and `scripts/board.py` read exactly this. Tickets are written fully before any work
starts, because a worker has only its own context and the ticket.

## Contents

- One writer per file
- Layout
- prd.md
- eval.md
- Status
- Concurrency
- Worked example

## One writer per file

A file that a human and a script both write can always lose an edit: a human editor honours no
lock, so no lock and no hash check can close the window (two such designs were built and failed
review). So nothing is shared. Each file has exactly one writer:

| File | Written by | Router may |
|---|---|---|
| `prd.md`, `eval.md` | the human (the router drafts them before approval) | read |
| `APPROVED` | **the human only**: creates it by hand, or runs `board.py approve NNN` | read; never write or delete |
| `status` | **the router only**, through `board.py set` | write |
| `board.md` | **generated** by `board.py render` and by every `set` | regenerate; nothing reads it back |
| `notes/` | the worker | read |

`board.py approve` creates `APPROVED` with an exclusive create and does nothing else; it is the
only code that writes that file and nothing in the script deletes it. The router never runs it.

## Layout

```
specs/tickets/
  board.md                  generated view: do not edit, nothing reads it back
  001-login-form/
    prd.md
    eval.md
    APPROVED                human-created: the ticket is approved
    status                  router-written: doing worker=thr_a1b2
    notes/                  worker output: results, screenshots, logs
  002-session-api/
    prd.md
    eval.md
```

The folder name is `<id>-<slug>`: `id` is 3 or more digits, `slug` is lowercase words joined by
hyphens. `board.py validate` fails on any other `NNN-` folder name and on a missing or blank
`prd.md` or `eval.md`.

## prd.md

Starts with front matter (the board reads only these two keys; the human owns the file):

```
---
mode: solo                          # solo, or team
runs: after 001, 003: needs the API # alongside, or after NNN[, NNN]: reason (reason required)
---
```

`mode` is `solo` (one worker, no child threads) or `team` (the worker may use its own Cloudroom
child threads). Then the body:

1. **What**: the outcome, in plain words.
2. **Scope**: files or areas it may change.
3. **Not touching**: files, areas and behaviours that must stay as they are.
4. **Decisions made**: choices already settled, so the worker does not reopen them.
5. **Context**: links to the specs, tickets or code it needs. Nothing it can find itself.

## eval.md

How the router (not the worker) will judge the result. Every line must be checkable from
evidence:

1. **Checks**: numbered, each with the exact command or page and the expected result.
2. **Edge cases**: the inputs most likely to break it.
3. **Definition of done**: the whole list that must hold, including repo gates and a draft PR
   through `pr-release-gate`.

## Status

A ticket's status is derived, never typed into a shared file:

- no `APPROVED` file, no `status` file: `draft`
- `APPROVED`, no `status` file: `ready`
- otherwise the `status` file: one line, `<ready|doing|review|done|blocked> [worker=thr_x] [was=<state>]`

`validate` rejects a `status` file with no `APPROVED`, a `doing` or `review` ticket without a
worker, a `blocked` without `was=ready|doing|review`, duplicate ids, unknown or self
dependencies, and dependency cycles. `set` runs `validate` on the whole folder first and refuses
every move not in this table (a draft cannot be moved at all: only the human's `APPROVED` ends a draft):

| From | To | Condition |
|---|---|---|
| `ready` | `doing` | worker id given; every `after` dependency is `done` |
| `doing` | `review` | the ticket has a worker |
| `review` | `doing` | fix-back; the worker is kept |
| `review` | `done` | (`done` is reachable from nowhere else) |
| `doing` | `doing` | with a new `--worker`: hand a lost worker's ticket to its replacement |
| `ready`, `doing`, `review` | `blocked` | records `was=<state>`, keeps the worker |
| `blocked` | the `was=` state | only back where it came from |

`next` lists only approved, `ready` tickets whose every dependency is `done`, within `--cap`
minus the tickets already `doing`, and refuses to list anything while the folder fails `validate`.
`board.md` is never an input: editing, deleting or corrupting it changes nothing.

## Concurrency

There is no lock because there is nothing to lock: the router is the only writer of each
`status` file, the human is the only writer of each `APPROVED`, and they never touch the same
file. Each `status` write is a temp file, `fsync`, then rename, so a crash leaves the old content
whole. The tests make a human create `APPROVED` before the router reads, after it reads, during
the `fsync` and just before the rename: it always survives.

A `set` regenerates `board.md` last, best effort (a stale view is harmless, and `render` rebuilds
it). Two `set` calls at the same moment on different tickets both land (different files); the view
may show only one until the next `render`.

## Worked example

```
specs/tickets/001-tenant-col/    APPROVED  status: done worker=thr_a1b2
specs/tickets/002-list-api/      APPROVED  status: doing worker=thr_c3d4   runs: after 001: needs the column
specs/tickets/003-list-page/     APPROVED  (no status = ready)             runs: after 002: calls the list API
specs/tickets/004-csv-export/    (no APPROVED = draft)
```

`specs/tickets/002-list-api/prd.md`

```markdown
---
mode: solo
runs: after 001: needs the column
---
# 002 list-api
## What
GET /api/jobs returns the signed-in tenant's jobs, newest first, 25 per page.
## Scope
src/app/api/jobs/route.ts, src/lib/jobs.ts and their tests.
## Not touching
Database migrations, the auth middleware, any page component.
## Decisions made
Cursor pagination on created_at. No offset paging.
## Context
Column added in ticket 001 (specs/tickets/001-tenant-col/).
```

`specs/tickets/002-list-api/eval.md`

```markdown
# 002 eval
## Checks
1. `npm test -- jobs` passes; the output is saved in notes/test.txt.
2. A request as tenant A never returns tenant B's rows (test named in notes/test.txt).
3. `curl` with a cursor returns the next 25 and no duplicates.
## Edge cases
Empty tenant (returns `[]`, not 404); exactly 25 rows; two rows with the same created_at.
## Definition of done
Checks 1-3 met, repo gates pass on the final commit, draft PR opened through pr-release-gate,
PR link and commit SHA in the final message.
```

Moving things along, with `b` as defined in SKILL.md:

```
b next --cap 3           ->  (nothing: 003 waits for 002, 004 is a draft)
b set 002 review         ->  002: doing -> review
b set 002 done           ->  002: review -> done
b next --cap 3           ->  003 list-page team
b set 004 doing --worker thr_x  ->  REFUSED: not approved: only the human can approve a ticket
b approve 004            ->  004: approved     (the human runs this, never the router)
```
