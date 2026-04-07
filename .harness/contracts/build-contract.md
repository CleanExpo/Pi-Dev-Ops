# Build Contract — Input/Output Agreement

## Purpose

Defines the explicit contract between the API layer and the build pipeline. Any caller of `create_session()` or `POST /api/build` must satisfy the input contract. The pipeline guarantees the output contract.

---

## Input Contract

```json
{
  "repo_url": "string (required) — must start with https:// or git@",
  "brief": "string (optional) — raw task description; defaults to full codebase analysis",
  "model": "string (optional) — one of: opus, sonnet, haiku; default: sonnet",
  "intent": "string (optional) — one of: feature, bug, chore, spike, hotfix; auto-classified if omitted",
  "evaluator_enabled": "boolean (optional) — default: true (from config TAO_EVALUATOR_ENABLED)"
}
```

**Validation rules (enforced in `main.py`):**
- `repo_url` must not be empty
- `repo_url` must start with `https://` or `git@` (no local paths)
- `model` must be in `ALLOWED_MODELS` (`config.py`)
- `intent` if provided must be in `{feature, bug, chore, spike, hotfix}`

---

## Output Contract

A `BuildSession` object is created immediately and its `id` returned. The build runs async.

**Session lifecycle states (in order):**

| State | Description |
|-------|-------------|
| `created` | Session object initialised, task queued |
| `cloning` | `git clone --depth 1` in progress |
| `building` | `claude -p` subprocess running |
| `evaluating` | Evaluator tier grading output |
| `complete` | All phases done, changes pushed |
| `failed` | Any phase failed (clone, build, or git error) |
| `killed` | Terminated by `POST /api/sessions/{sid}/kill` |
| `interrupted` | In-flight state detected on server restart |

**WebSocket stream:** `GET /ws/build/{sid}`
- Emits `{type, text, ts}` objects in real-time
- `type` values: `phase`, `system`, `agent`, `tool`, `output`, `success`, `error`, `metric`, `stderr`, `done`
- Final message: `{type: "done", status: "<final-state>"}`

**Persistence:** Session JSON written to `{TAO_LOGS}/sessions/{sid}.json` after every status change.

---

## Error Guarantee

If any phase fails:
- `session.status` is set to `"failed"`
- `session.error` is populated with the failure reason
- WebSocket receives `{type: "error", text: "..."}` before closing
- Session is persisted to disk for post-mortem inspection
