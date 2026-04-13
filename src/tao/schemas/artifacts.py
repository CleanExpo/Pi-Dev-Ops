from dataclasses import dataclass, field
from typing import Optional
import uuid

@dataclass
class TaskSpec:
    description: str
    tier: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    context: str = ''
    parent_task_id: Optional[str] = None
    expected_output: str = ''
    max_tokens: int = 4096

@dataclass
class TaskResult:
    task_id: str
    tier: str
    content: str
    success: bool = True
    tokens_used: int = 0
    model: str = ''
    duration_seconds: float = 0.0

@dataclass
class Escalation:
    task_id: str
    from_tier: str
    reason: str
    context_needed: str = ''
    partial_result: Optional[str] = None
