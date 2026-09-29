---
name: gs-freeze
description: Lock Edit and Write to one directory for this session only, so a debugging or autonomous run cannot drift into "fixing" unrelated code. Use for "freeze edits to X", "only edit this folder", "lock the scope", "unfreeze", or at the start of any investigate/fix run that should touch one module.
allowed-tools:
  - Bash(python3 *check_freeze.py*)
  - Read
hooks:
  PreToolUse:
    - matcher: "Edit|Write|NotebookEdit"
      hooks:
        - type: command
          command: "python3 \"$HOME/.claude/skills/gs-freeze/bin/check_freeze.py\""
          statusMessage: "Checking freeze boundary..."
metadata:
  source: garrytan/gstack freeze + unfreeze
  source_sha: b9706f3635b6a545f46fae607ae9d6bcbfb69b91
  license: MIT
---

# gs-freeze: keep a run inside one directory

The hook lives in this skill's frontmatter, so it runs only while the skill is active. Nothing is
written to `settings.json`.

## Set the boundary

Pick the smallest directory the task needs. Infer it from the task; ask only if the task names
none, and offer the likeliest directory as the recommended default.

```bash
python3 ~/.claude/skills/gs-freeze/bin/check_freeze.py set <dir>
```

From then on, any Edit, Write or NotebookEdit outside `<dir>` is denied with a reason.

## Check or lift it

```bash
python3 ~/.claude/skills/gs-freeze/bin/check_freeze.py status
python3 ~/.claude/skills/gs-freeze/bin/check_freeze.py clear
```

## What it does and does not do

- The freeze belongs to one session, `~/.local/state/gs/freeze/<session-id>.txt`. Other agents
  running at the same time are not affected. (Upstream gstack uses one global file. Here, that
  would let one agent's freeze block every other agent.)
- It fails closed. A payload it cannot read, or an internal error, blocks the edit.
- Symlinks and `..` are resolved before the check, so a link inside the boundary that points
  outside it is still blocked.
- It stops accidents, not attacks. Bash commands such as `sed -i` can still write anywhere.
  Treat it as a scope guard, not a security boundary.

Adapted from garrytan/gstack @ `b9706f36` (MIT). See `NOTICE.md`.
