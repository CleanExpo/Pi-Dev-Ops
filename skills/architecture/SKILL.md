---
name: architecture
description: Pi Dev Ops architectural principles — companion model, sandbox isolation, ZTE leverage points, CLAUDE.md maintenance, full-clearance sprint patterns.
---

# Architecture Best Practices

Apply when making structural decisions about Pi Dev Ops — session handling, workspace isolation, pipeline design, or documentation strategy.

## Core Model

Pi Dev Ops is a **split-screen companion**: Left = Claude Desktop CLI writing code; Right = Pi Dev Ops orchestrating, tracking, and pushing to Linear. It is NOT a standalone IDE. Every architectural decision must serve this companion model.

## Rules

- **CLAUDE.md is the highest-leverage documentation fix.** It is loaded into every future Claude session. Keeping it accurate (file map, conventions, smoke tests) eliminates all ramp-up time for AI sessions. Update it whenever the architecture changes.

- **Sandbox = workspace directory.** Each session gets an isolated clone at `app/workspaces/{session_id}/`. Sandbox enforcement means verifying the workspace exists before Phase 4 and refusing to run `claude -p` outside it.

- **Full-clearance sprints outperform gated execution 10×.** All Priority 1+2 items complete faster in a single no-authority-gates sprint than issue-by-issue with approval loops.

- **ZTE leverage points with highest ROI:** CLAUDE.md population (+4 pts), evaluator tier (+2), webhook triggers (+2), PITER+ADW (+4). Prioritise these when choosing what to build next.
