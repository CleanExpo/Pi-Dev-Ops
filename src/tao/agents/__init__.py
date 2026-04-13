"""
agents/__init__.py — AgentDispatcher for TAO orchestration.

Routes work to skills based on intent, manages agent lifecycle,
and provides unified interface for multi-agent coordination.

Interfaces with:
  - skills.py — skill loading and intent mapping
  - orchestrator.py — fan-out execution
  - sessions — work session management
"""

import asyncio
import logging
from typing import Any
from dataclasses import dataclass

from ..skills import skills_for_intent, load_all_skills

logger = logging.getLogger(__name__)


@dataclass
class AgentTask:
    """Represents a unit of work for an agent."""

    intent: str  # feature | bug | chore | spike | hotfix
    brief: str  # detailed work description
    context: dict[str, Any]  # repo_url, repo_name, branch, etc.
    metadata: dict[str, Any]  # priority, deadline, tags, etc.


@dataclass
class AgentResult:
    """Result from agent execution."""

    success: bool
    intent: str
    skills_used: list[str]
    output: str
    artifacts: dict[str, Any]  # generated files, PRs, issues, etc.
    metrics: dict[str, Any]  # execution time, tokens, quality scores, etc.


class AgentDispatcher:
    """
    Multi-agent orchestrator for TAO skill execution.

    Routes tasks to relevant skills based on intent, manages parallel
    execution, and aggregates results across agents.
    """

    def __init__(self, max_concurrent: int = 4):
        """Initialize dispatcher with optional concurrency limit."""
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_agents = {}  # task_id -> agent_handle

    async def dispatch(self, task: AgentTask) -> AgentResult:
        """
        Dispatch a task to the appropriate agent(s) based on intent.

        Selects relevant skills, executes them in sequence or parallel,
        and aggregates results.
        """
        logger.info(f"Dispatching task: intent={task.intent}, brief={task.brief[:50]}...")

        try:
            async with self._semaphore:
                # Select skills for this intent
                skills = skills_for_intent(task.intent)
                if not skills:
                    logger.warning(f"No skills found for intent: {task.intent}")
                    return AgentResult(
                        success=False,
                        intent=task.intent,
                        skills_used=[],
                        output="No matching skills for this intent",
                        artifacts={},
                        metrics={"error": "no_skills"},
                    )

                # Execute skills
                results = await self._execute_skills(
                    skills, task.intent, task.brief, task.context, task.metadata
                )
                return results

        except Exception as e:
            logger.error(f"Agent dispatch failed: {e}")
            return AgentResult(
                success=False,
                intent=task.intent,
                skills_used=[],
                output=f"Dispatch error: {str(e)}",
                artifacts={},
                metrics={"error": str(e)},
            )

    async def _execute_skills(
        self,
        skills: list[dict],
        intent: str,
        brief: str,
        context: dict,
        metadata: dict,
    ) -> AgentResult:
        """Execute a sequence of skills and aggregate results."""
        skills_used = []
        artifacts = {}
        execution_log = []

        for skill in skills:
            skill_name = skill["name"]
            logger.info(f"Executing skill: {skill_name}")

            try:
                # Execute skill (placeholder for now)
                # In real implementation, would call appropriate executor
                # based on skill type (python, shell, claude-api, etc.)

                skill_result = await self._execute_single_skill(
                    skill, intent, brief, context, metadata
                )

                if skill_result["success"]:
                    skills_used.append(skill_name)
                    artifacts.update(skill_result.get("artifacts", {}))
                    execution_log.append(
                        f"✓ {skill_name}: {skill_result.get('message', 'completed')}"
                    )
                else:
                    execution_log.append(
                        f"✗ {skill_name}: {skill_result.get('message', 'failed')}"
                    )

            except Exception as e:
                logger.error(f"Skill execution failed: {skill_name}: {e}")
                execution_log.append(f"✗ {skill_name}: {str(e)}")

        return AgentResult(
            success=len(skills_used) > 0,
            intent=intent,
            skills_used=skills_used,
            output="\n".join(execution_log),
            artifacts=artifacts,
            metrics={"skills_executed": len(skills_used), "total_skills": len(skills)},
        )

    async def _execute_single_skill(
        self, skill: dict, intent: str, brief: str, context: dict, metadata: dict
    ) -> dict:
        """Execute a single skill (placeholder for executor routing)."""
        # This would route to appropriate executor based on skill type
        # For now, return a stub result
        return {
            "success": True,
            "message": f"Skill '{skill['name']}' executed",
            "artifacts": {},
        }

    async def batch_dispatch(self, tasks: list[AgentTask]) -> list[AgentResult]:
        """Dispatch multiple tasks in parallel."""
        logger.info(f"Batch dispatching {len(tasks)} tasks")
        results = await asyncio.gather(
            *[self.dispatch(task) for task in tasks],
            return_exceptions=True,
        )
        return [
            r if isinstance(r, AgentResult) else self._exception_to_result(r, "")
            for r in results
        ]

    def _exception_to_result(self, exc: Exception, intent: str) -> AgentResult:
        """Convert exception to AgentResult."""
        return AgentResult(
            success=False,
            intent=intent,
            skills_used=[],
            output=f"Batch dispatch error: {str(exc)}",
            artifacts={},
            metrics={"error": str(exc)},
        )

    def get_available_skills(self) -> list[str]:
        """List all available skills."""
        return list(load_all_skills().keys())

    def get_skills_for_intent(self, intent: str) -> list[str]:
        """Get skill names for a specific intent."""
        return [s["name"] for s in skills_for_intent(intent)]


# Global dispatcher instance
_dispatcher: AgentDispatcher | None = None


def get_dispatcher(max_concurrent: int = 4) -> AgentDispatcher:
    """Get or create the global dispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AgentDispatcher(max_concurrent=max_concurrent)
    return _dispatcher


def reset_dispatcher() -> None:
    """Reset the global dispatcher (for testing)."""
    global _dispatcher
    _dispatcher = None
