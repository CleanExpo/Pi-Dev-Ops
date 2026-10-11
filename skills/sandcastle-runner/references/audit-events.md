Moved from SKILL.md. Read when adding or reviewing the sandcastle audit event types.

## Audit events emitted

Add to `swarm/audit_emit.py::_VALID_TYPES`:

```python
# Wave 5 / RA-1856 — Sandcastle
"sandcastle_run_started",   # one per launch; fields: run_id, agent, sandbox, branch
"sandcastle_run_ok",        # one per successful completion; fields: run_id, duration_s, commits_count
"sandcastle_run_failed",    # one per failure; fields: run_id, failure_reason, exit_code
"sandcastle_env_resolved",  # one per launch; fields: run_id, var_count, project_slug — NAMES NOT VALUES
```

Existing `audit_emit._maybe_redact` handles long-string redaction; we add the regex strip on top for the specific shape `KEY=value` that the redactor's >32-char heuristic might miss for short keys.
