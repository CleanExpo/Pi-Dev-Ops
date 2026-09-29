---
name: nlm-skill
description: "Expert guide for the NotebookLM CLI (`nlm`) and MCP server - interfaces for Google NotebookLM. Use this skill when users want to interact with NotebookLM programmatically, including: creating/managing notebooks, adding sources (URLs, YouTube, text, Google Drive), generating content (podcasts, reports, quizzes, flashcards, mind maps, slides, infographics, videos, data tables), conducting research, chatting with sources, or automating NotebookLM workflows. Triggers on mentions of \"nlm\", \"notebooklm\", \"notebook lm\", \"podcast generation\", \"audio overview\", or any NotebookLM-related automation task."
---

# NotebookLM CLI & MCP Expert

This skill provides guidance for using NotebookLM via both the `nlm` CLI and MCP tools. The
full command catalog lives in `references/` and is loaded on demand — see
[Command & tool reference](#command--tool-reference) below.

## Tool Detection (CRITICAL - Read First!)

**ALWAYS check which tools are available before proceeding:**

1. **Check for MCP tools**: Look for tools starting with `mcp__notebooklm-mcp__*` or `mcp_notebooklm_*`
2. **If BOTH MCP tools AND CLI are available**: **ASK the user** which they prefer to use before proceeding
3. **If only MCP tools are available**: Use them directly (refer to tool docstrings for parameters)
4. **If only CLI is available**: Use `nlm` CLI commands via Bash

**Decision Logic:**
```
has_mcp_tools = check_available_tools()  # Look for mcp__notebooklm-mcp__* or mcp_notebooklm_*
has_cli = check_bash_available()  # Can run nlm commands

if has_mcp_tools and has_cli:
    # ASK USER: "I can use either MCP tools or the nlm CLI. Which do you prefer?"
    user_preference = ask_user()
else if has_mcp_tools:
    # Use MCP tools directly
    mcp__notebooklm-mcp__notebook_list()
else:
    # Use CLI via Bash
    bash("nlm notebook list")
```

This skill documents BOTH approaches. Choose the appropriate one based on tool availability and **user preference**.

## Quick Reference

**Run `nlm --ai` to get comprehensive AI-optimized documentation** - this provides a complete view of all CLI capabilities.

```bash
nlm --help              # List all commands
nlm <command> --help    # Help for specific command
nlm --ai                # Full AI-optimized documentation (RECOMMENDED)
nlm --version           # Check installed version
```

## Critical Rules (Read First!)

1. **Always authenticate first**: Run `nlm login` before any operations
2. **Sessions expire in ~20 minutes**: Re-run `nlm login` if commands start failing
3. **⚠️ ALWAYS ASK USER BEFORE DELETE**: Before executing ANY delete command, ask the user for explicit confirmation. Deletions are **irreversible**. Show what will be deleted and warn about permanent data loss.
4. **`--confirm` is REQUIRED**: All generation and delete commands need `--confirm` or `-y` (CLI) or `confirm=True` (MCP)
5. **Research requires `--notebook-id`**: The flag is mandatory, not positional
6. **Capture IDs from output**: Create/start commands return IDs needed for subsequent operations
7. **Use aliases**: Simplify long UUIDs with `nlm alias set <name> <uuid>`
8. **Check aliases before creating**: Run `nlm alias list` before creating a new alias to avoid conflicts with existing names.
9. **DO NOT launch REPL**: Never use `nlm chat start` - it opens an interactive REPL that AI tools cannot control. Use `nlm notebook query` for one-shot Q&A instead.
10. **Choose output format wisely**: Default output (no flags) is compact and token-efficient—use it for status checks. Use `--quiet` to capture IDs for piping. Only use `--json` when you need to parse specific fields programmatically.
11. **Use `--help` when unsure**: Run `nlm <command> --help` to see available options and flags for any command.

## Workflow Decision Tree

Use this to determine the right sequence of commands:

```
User wants to...
│
├─► Work with NotebookLM for the first time
│   └─► nlm login → nlm notebook create "Title"
│
├─► Add content to a notebook
│   ├─► From a URL/webpage → nlm source add <nb-id> --url "https://..."
│   ├─► From YouTube → nlm source add <nb-id> --url "https://youtube.com/..."
│   ├─► From pasted text → nlm source add <nb-id> --text "content" --title "Title"
│   ├─► From Google Drive → nlm source add <nb-id> --drive <doc-id> --type doc
│   └─► Discover new sources → nlm research start "query" --notebook-id <nb-id>
│
├─► Generate content from sources
│   ├─► Podcast/Audio → nlm audio create <nb-id> --confirm
│   ├─► Written summary → nlm report create <nb-id> --confirm
│   ├─► Study materials → nlm quiz/flashcards create <nb-id> --confirm
│   ├─► Visual content → nlm mindmap/slides/infographic create <nb-id> --confirm
│   ├─► Video → nlm video create <nb-id> --confirm
│   └─► Extract data → nlm data-table create <nb-id> "description" --confirm
│
├─► Ask questions about sources
│   └─► nlm notebook query <nb-id> "question"
│       (Use --conversation-id for follow-ups)
│       ⚠️ Do NOT use `nlm chat start` - it's a REPL for humans only
│
├─► Check generation status
│   └─► nlm studio status <nb-id>
│
└─► Manage/cleanup
    ├─► List notebooks → nlm notebook list
    ├─► List sources → nlm source list <nb-id>
    ├─► Delete source → nlm source delete <source-id> --confirm
    └─► Delete notebook → nlm notebook delete <nb-id> --confirm
```

## Output Formats

Most list commands support multiple formats:

| Flag | Description |
|------|-------------|
| (none) | Rich table (human-readable) |
| `--json` | JSON output (for parsing) |
| `--quiet` | IDs only (for piping) |
| `--title` | "ID: Title" format |
| `--url` | "ID: URL" format (sources only) |
| `--full` | All columns/details |

## Command & tool reference

The full catalog lives in `references/` — load the file that matches the surface you are on:

- **CLI commands** (`nlm ...`) — every command, flag, and enum, including the batch / cross /
  pipeline / tag / skill families and the content-generation style enums:
  [`references/command_reference.md`](references/command_reference.md)
- **MCP tools** (`mcp__notebooklm-mcp__*`) — tool names, parameters, the `studio_create`
  artifact-type table, and `confirm=True` semantics: [`references/mcp-tools.md`](references/mcp-tools.md)
- **End-to-end workflows** — research→podcast, study materials, Drive sync, batch &
  cross-notebook: [`references/workflows.md`](references/workflows.md)
- **Errors, recovery, and rate limits**: [`references/troubleshooting.md`](references/troubleshooting.md)

For the live, complete CLI documentation at any time, run `nlm --ai`.
