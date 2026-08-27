"""File Linear sub-issues under an approved Goal ticket."""
from __future__ import annotations

from typing import Any, Callable

from .goal_analyze_fields import normalize_sub_tasks

GqlFn = Callable[..., dict[str, Any]]


def file_sub_tasks(
    repo: str,
    draft: dict[str, Any],
    *,
    parent_id: str,
    parent_goal: str,
    project_title: str,
    file_goal: Callable[..., dict[str, Any]],
    gql: GqlFn | None,
) -> dict[str, Any]:
    if not parent_id:
        return {"tickets": []}
    created: list[dict[str, Any]] = []
    parent_acc = str(draft.get("acceptance") or "")
    for child in normalize_sub_tasks(draft.get("sub_tasks_json") or draft.get("sub_tasks")):
        notes = "\n\n".join(
            part
            for part in (
                child.get("description") or "",
                f"## Scenarios\n{child['scenarios']}" if child.get("scenarios") else "",
                f"## Details\n{child['details']}" if child.get("details") else "",
            )
            if part
        )
        child_goal = child.get("description") or f"Complete sub-task: {child['title']}"
        child_acc = child.get("acceptance") or parent_acc
        out = file_goal(
            child_goal,
            repo,
            child_acc,
            gql=gql,
            title=child["title"],
            notes=notes,
            parent_goal=parent_goal,
            parent_id=parent_id,
            project_title=project_title,
        )
        if out.get("error"):
            return {
                "error": out["error"],
                "fields": out.get("fields"),
                "failed_title": child["title"],
            }
        created.append(out)
    return {"tickets": created}
