---
name: linear-computer-use
description: Use Chrome browser to interact with Linear visually — read the board, pick up tasks assigned by board members, implement them autonomously. Triggered by "open Linear", "check the board", or "do what's on the Linear board".
---

# Linear Computer-Use Skill

Uses Chrome browser control to interact with Linear.app visually, exactly as a human board member would. Combines visual board reading with autonomous code implementation.

## When to Use This Skill
- Board members have added tasks with context/screenshots that aren't fully in the issue description
- You need to see the full board layout (epics, groupings, priorities) visually
- The Linear MCP is unavailable or returning incomplete data
- The user says "open Linear" or "check what's on the board"

## Linear URLs
- Board: https://linear.app/unite-hub/team/RA/board
- Issues list: https://linear.app/unite-hub/team/RA/issues
- Project: https://linear.app/unite-hub/project/restoreassist-compliance-platform-3308dafd46b3/issues

## Workflow

### Phase 1 — Read the Board Visually

1. Open Linear board in Chrome:
```
mcp__Claude_in_Chrome__navigate url="https://linear.app/unite-hub/team/RA/board"
```

2. Take a screenshot to see current board state:
```
mcp__Claude_in_Chrome__take_screenshot
```

3. Read the page text to extract all issue titles and IDs:
```
mcp__Claude_in_Chrome__get_page_text
```

4. For each Todo/Backlog issue visible, click to open it and read full description:
```
mcp__Claude_in_Chrome__find description="RA-XXX issue card"
mcp__Claude_in_Chrome__browser_click ref=<ref>
mcp__Claude_in_Chrome__get_page_text
```

### Phase 2 — Extract Task Requirements

For each issue found:
- Note the issue ID (RA-NNN), title, priority indicator, and description
- Check comments for additional context from board members
- Note any attachments or linked designs
- Add to a work queue ordered by priority (🔴 Urgent > 🟠 High > 🟡 Normal > 🔵 Low)

### Phase 3 — Implement Each Task

For each task in the work queue (max 8 per session):

1. **Switch to implementation mode** — work in D:\RestoreAssist using direct tools
2. Follow the full implementation loop from `linear-task-processor` agent:
   - Move to In Progress (via Linear MCP or browser)
   - Branch off sandbox
   - Read source files
   - Implement
   - Type-check + lint
   - Commit + PR
   - Move to In Review

3. **Update Linear via browser** if MCP fails:
```
mcp__Claude_in_Chrome__navigate url="https://linear.app/unite-hub/team/RA/issues/RA-NNN"
# Change status to In Review
mcp__Claude_in_Chrome__find description="status button"
mcp__Claude_in_Chrome__browser_click ref=<ref>
# Add PR comment
mcp__Claude_in_Chrome__find description="comment input"
mcp__Claude_in_Chrome__form_input ref=<ref> value="PR ready: [url]"
```

### Phase 4 — Board Verification

After completing all tasks, take a final screenshot to confirm the board state:
```
mcp__Claude_in_Chrome__take_screenshot
```
Report: how many tasks completed, which PRs created, what remains on the board.

## Error Handling
- If Linear requires login: navigate to https://linear.app/unite-hub and check for auth state. Do NOT attempt to log in — report to user that browser session needs authentication.
- If a page element isn't found by text: use `find` with a broader description
- If navigation fails: retry once, then fall back to Linear MCP tools

## Important
- Never stop between tasks — complete the full loop for each issue before moving to the next
- Document all autonomous decisions in PR descriptions
- If an issue has context only visible in screenshots/attachments, describe what you see in the PR
