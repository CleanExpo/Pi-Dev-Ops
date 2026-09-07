"""Visible sub-task edits must file, not the stale analyze JSON."""
from app.server.goal_analyze_fields import encode_sub_tasks, format_sub_tasks, normalize_sub_tasks
from app.server.goal_ticket_children import sub_task_source


def test_sub_task_source_keeps_json_when_textarea_matches_render() -> None:
    raw = [
        {
            "title": "Add the title field",
            "description": "Required title persists after save.",
            "scenarios": "Given empty title When submit Then show an error",
            "details": "Trim whitespace",
            "acceptance": "Empty title is rejected with an error.",
        }
    ]
    encoded = encode_sub_tasks(raw)
    draft = {
        "sub_tasks": format_sub_tasks(normalize_sub_tasks(raw)),
        "sub_tasks_json": encoded,
    }
    assert sub_task_source(draft) == encoded


def test_sub_task_source_uses_visible_text_after_operator_edit() -> None:
    draft = {
        "sub_tasks": "1. Persist saved looks after refresh",
        "sub_tasks_json": encode_sub_tasks(
            [{"title": "Original child", "description": "Old child from analyze."}]
        ),
    }
    children = normalize_sub_tasks(sub_task_source(draft))
    assert children[0]["title"] == "1. Persist saved looks after refresh"


def test_sub_task_source_falls_back_to_text_when_json_empty() -> None:
    draft = {"sub_tasks": "1. Add sign-in for guests", "sub_tasks_json": ""}
    children = normalize_sub_tasks(sub_task_source(draft))
    assert children[0]["title"] == "1. Add sign-in for guests"
