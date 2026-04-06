---
name: hooks-system
description: Lifecycle hooks for agent observability and safety.
---

# Hooks System

## 6 Hook Types
1. PreToolUse - Block dangerous commands
2. PostToolUse - Log every action
3. Stop - Enforce completion criteria
4. SubagentStop - Track parallel completion
5. PreCompact - Backup context before compaction
6. SessionStart - Load handoff from previous session
