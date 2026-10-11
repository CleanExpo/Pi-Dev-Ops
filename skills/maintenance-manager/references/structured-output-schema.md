> Moved from SKILL.md. Read when emitting the structured JSON output for a maintenance audit.

### 2. OpenAI Structured Output Schema

Every invocation emits JSON matching the skill-specific schema. Common fields across all skills:

```json
{
  "version": "3.1",
  "skill_name": "",
  "invoked_at": "ISO-8601",
  "task_summary": "",
  "model_used": "",
  "duration_seconds": 0.0,
  "tool_calls": {},
  "tokens": {"prompt": 0, "completion": 0},
  "self_review_score": 0.0,
  "confidence": 0.0,
  "success": true,
  "audit_trace_hash": "sha256",
  "improvement_queued": false
}
```
