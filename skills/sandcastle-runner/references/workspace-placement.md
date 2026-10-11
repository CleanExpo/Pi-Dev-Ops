Moved from SKILL.md. Read when deciding where a Sandcastle worktree lives per environment.

## Workspace placement

| Environment | Worktree path | Reason |
|---|---|---|
| Local | `/tmp/pi-ceo-workspaces/sandcastle/{session_id}/` | Same root as existing weak-sandbox; gc.py covers it |
| Railway | `/tmp/pi-ceo-workspaces/sandcastle/{session_id}/` | Railway tmpfs |
| Vercel sandbox provider | inside microVM, not host | Sandcastle handles internally; we set `bindMount: false` |
