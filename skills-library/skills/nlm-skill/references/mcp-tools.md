# NotebookLM MCP Tools — Reference

MCP-tool counterpart to the CLI `command_reference.md`. Loaded on demand when working through MCP (`mcp__notebooklm-mcp__*`) rather than the CLI.

All tools are exposed under the `mcp__notebooklm-mcp__*` prefix (some hosts surface them as `mcp_notebooklm_*`). Refer to each tool's own docstring for the authoritative parameter list; this file captures the documented parameters, enums, and behavioral notes.

**Universal rules**
- Destructive and generative actions require `confirm=True` (the MCP equivalent of the CLI `--confirm` / `-y`). This applies to deletes, Drive sync, and all artifact generation.
- ALWAYS ask the user for explicit confirmation before any delete — deletions are irreversible.
- MCP and the CLI share the same authentication backend; authenticating with one works for both.

---

## 1. Authentication

The MCP server always uses the **active default profile**. To switch which Google account the MCP server talks to, you MUST use the CLI (`nlm login switch <name>`); the next MCP tool call instantly uses the new account. There is no MCP tool to switch profiles.

MCP auth tools:
- **`refresh_auth()`** — reload auth tokens into the MCP server after running CLI auth. Use this if MCP tools hit authentication errors: run `nlm login` (works for both CLI and MCP), then call `refresh_auth()`.
- **`save_auth_tokens(cookies="<cookie_header>")`** — fallback method. Manually save cookies extracted from Chrome DevTools (pass the cookie header string).

Session lifetime is ~20 minutes; re-authenticate when calls fail with auth errors.

---

## 2. Notebook Management

Tools: **`notebook_list`**, **`notebook_create`**, **`notebook_get`**, **`notebook_describe`**, **`notebook_query`**, **`notebook_rename`**, **`notebook_delete`**.

- All accept a `notebook_id` parameter.
- `notebook_delete` requires `confirm=True`.
- `notebook_describe` returns an AI-generated summary plus suggested topics.
- `notebook_query` is one-shot Q&A over the notebook's sources (use `--conversation-id`/conversation continuation semantics for follow-ups, mirroring the CLI).

---

## 3. Source Management

**`source_add`** — add a source. Use the `source_type` parameter with one of:
- `url` — web page or YouTube URL (`url` param)
- `text` — pasted content (`text` + `title` params)
- `file` — local file upload (`file_path` param)
- `drive` — Google Drive doc (`document_id` + `doc_type` params)

**Drive `doc_type` values**: `doc`, `slides`, `sheets`, `pdf`

Other source tools:
- **`source_list_drive`** — list Drive sources (with freshness).
- **`source_describe`** — AI summary + keywords for a source.
- **`source_get_content`** — raw text content of a source.
- **`source_rename`** — rename a source. Signature: `source_rename(notebook_id, source_id, new_title)`.
- **`source_sync_drive`** — sync stale Drive sources. Requires `confirm=True`.
- **`source_delete`** — delete a source. Requires `confirm=True`.

---

## 4. Research (Source Discovery)

Research finds NEW sources from the web or Google Drive.

**`research_start`** parameters:
- `source`: `web` or `drive`
- `mode`: `fast` (~30s, ~10 sources) or `deep` (~5min, ~40+ sources, web only)

Workflow: **`research_start`** → poll **`research_status`** → **`research_import`**.

---

## 5. Content Generation (Studio) — Unified Creation

**`studio_create`** — single tool for all artifact generation. Pass `artifact_type` plus the type-specific options below. All require `confirm=True`.

| `artifact_type` | Key Options |
|--------------|-------------|
| `audio` | `audio_format`: deep_dive / brief / critique / debate · `audio_length`: short / default / long |
| `video` | `video_format`: explainer / brief · `visual_style`: auto_select / classic / whiteboard / kawaii / anime / watercolor / retro_print / heritage / paper_craft |
| `report` | `report_format`: Briefing Doc / Study Guide / Blog Post / Create Your Own · `custom_prompt` |
| `quiz` | `question_count` · `difficulty`: easy / medium / hard |
| `flashcards` | `difficulty`: easy / medium / hard |
| `mind_map` | `title` |
| `slide_deck` | `slide_format`: detailed_deck / presenter_slides · `slide_length`: short / default |
| `infographic` | `orientation`: landscape / portrait / square · `detail_level`: concise / standard / detailed · `infographic_style`: auto_select / sketch_note / professional / bento_grid / editorial / instructional / bricks / clay / anime / kawaii / scientific |
| `data_table` | `description` (REQUIRED) |

**Common options (all artifact types)**: `source_ids`, `language` (BCP-47 code, e.g. en/es/fr/de/ja), `focus_prompt`.

### Revise Slides — `studio_revise`

Revise individual slides in an existing slide deck.
- Requires `artifact_id` (from `studio_status`) and `slide_instructions`.
- Creates a NEW artifact — the original is not modified.
- Slide numbers are 1-based (slide 1 = first slide).
- Poll `studio_status` after calling to check when the new deck is ready.

---

## 6. Studio (Artifact Management)

- **`studio_status`** — check generation progress / list artifacts. Also used to rename an artifact: call with `action="rename"`, `artifact_id`, and `new_title`.
- **`download_artifact`** — download an artifact locally. Parameters: `artifact_type` and `output_path`.
- **`export_artifact`** — export to Google Docs/Sheets. Parameter `export_type`: `docs` or `sheets`.
- **`studio_delete`** — delete an artifact. Requires `confirm=True`.

**Status values**: `completed` (✓), `in_progress` (●), `failed` (✗).

**Prompt extraction (important note)**: `studio_status` returns a `custom_instructions` field for each artifact. This contains the original focus prompt or custom instructions used to generate that artifact (e.g. the prompt for a "Create Your Own" report, or the focus topic for an Audio Overview). Useful for retrieving the exact prompt that produced a successful artifact.

---

## 7. Chat Configuration and Notes

- **`chat_configure`** — configure chat behavior. Parameter `goal`: `default` / `learning_guide` / `custom`.
- **`note`** — manage notes. Parameter `action`: `create` / `list` / `update` / `delete`. Delete requires `confirm=True`.

> Note: there is no MCP REPL. For Q&A use `notebook_query` (one-shot). The CLI-only `nlm chat start` REPL is for human terminal users and cannot be driven by AI tools.

---

## 8. Notebook Sharing

- **`notebook_share_status`** — check current sharing settings.
- **`notebook_share_public`** — enable / disable the public link.
- **`notebook_share_invite`** — invite a collaborator. Parameters: `email` and `role` (`viewer` or `editor`).

---

## 9. Aliases (UUID Shortcuts)

Aliases are a **CLI-only** feature (`nlm alias set/get/list/delete`) — there is no dedicated MCP tool. MCP tools accept full UUIDs (and, where the host resolves them, aliases configured via the CLI). The MCP `batch`, `cross_notebook_query`, and `tag` tools instead let you target notebooks by `notebook_names` or `tags`.

---

## 10. Configuration

Configuration management (`nlm config show/get/set`) is **CLI-only** — there is no MCP config tool. The MCP server reads the same on-disk config, including `auth.default_profile`, which determines the account the MCP server uses (change it via `nlm login switch` or `nlm config set auth.default_profile <name>`).

---

## 11. Batch Operations

**`batch`** — perform the same action across multiple notebooks. Select notebooks by `notebook_names`, `tags`, or `all=True`. Use the `action` parameter.

```python
batch(action="query", query="What are the key findings?", notebook_names="AI Research, Dev Tools")
batch(action="add_source", source_url="https://example.com", tags="ai,research")
batch(action="create", titles="Project A, Project B, Project C")
batch(action="delete", notebook_names="Old Project", confirm=True)
batch(action="studio", artifact_type="audio", tags="research", confirm=True)
```

---

## 12. Cross-Notebook Query

**`cross_notebook_query`** — query multiple notebooks and get aggregated answers with per-notebook citations. Target by `notebook_names`, `tags`, or `all=True`.

```python
cross_notebook_query(query="Compare approaches", notebook_names="Notebook A, Notebook B")
cross_notebook_query(query="Summarize", tags="ai,research")
cross_notebook_query(query="Everything", all=True)
```

---

## 13. Pipelines

**`pipeline`** — define and execute multi-step notebook workflows.

```python
pipeline(action="list")  # List available pipelines
pipeline(action="run", notebook_id="...", pipeline_name="ingest-and-podcast", input_url="https://...")
```

**Built-in pipelines**: `ingest-and-podcast`, `research-and-report`, `multi-format`.

Create custom pipelines by adding YAML files to `~/.notebooklm-mcp-cli/pipelines/`.

---

## 14. Tags & Smart Select

**`tag`** — tag notebooks for organization and target batch operations by tag.

```python
tag(action="add", notebook_id="...", tags="ai,research,llm")
tag(action="remove", notebook_id="...", tags="ai")
tag(action="list")                           # List all tagged notebooks
tag(action="select", query="ai research")    # Find notebooks by tag match
```

---

## Server Info (Version Check)

**`server_info()`** — get version and check for updates. Returns: `version`, `latest_version`, `update_available`, `update_command`.

```python
mcp__notebooklm-mcp__server_info()
```
