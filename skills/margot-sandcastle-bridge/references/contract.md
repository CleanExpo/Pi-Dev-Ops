Moved from SKILL.md. Read when you need the input and output type definitions.

## Contract

### Input (per-research-completion)

```python
class MargotResearchCompletion:
    interaction_id: str
    body: str  # the research output from Margot
    originated_at: str  # ISO timestamp
    originating_session_id: str  # Pi-CEO session that requested the research
```

### Output (per-research-completion)

```python
class MargotIntentResult:
    interaction_id: str
    classification: Literal["action_shaped", "informational", "unknown"]
    confidence: float
    action_summary: str | None  # populated when action_shaped
    target_repo: str | None  # populated when action_shaped
    draft_id: str | None  # populated when action_shaped + draft posted
    skipped_reason: str | None  # populated when not action_shaped
```

### Output (post-reaction, when 👍)

```python
class MargotActionAccepted:
    interaction_id: str
    draft_id: str
    linear_issue_id: str  # the newly created issue
    linear_issue_identifier: str  # e.g. "RA-1900"
    labels_applied: list[str]
```
