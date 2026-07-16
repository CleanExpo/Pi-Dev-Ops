"""Test that create_linear_tickets embeds a structured grounding anchor in each ticket.

Import convention follows existing tests/test_plaud_actions.py:
- sys.path.insert scripts/ so bare `import plaud_actions` works
- Use pa.TicketRef, pa.Action (re-exported from linear_helpers)
"""
import sys
from pathlib import Path

# Insert scripts/ directory so bare imports resolve (matches test_plaud_actions.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import plaud_actions as pa
from app.server import grounding


def test_ticket_description_carries_resolvable_anchor(monkeypatch):
    captured = {}

    def fake_create_issue(*, api_key, title, description, team_id, project_id, priority):
        captured["description"] = description
        return pa.TicketRef(id="i9", identifier="RA-9", url="https://linear.app/x/RA-9")

    monkeypatch.setattr(pa, "create_linear_issue", fake_create_issue)

    action = pa.Action(title="Scan", description="Scan the flowchart", priority=3)
    refs = pa.create_linear_tickets(
        actions=[action],
        team_id="t",
        project_id="p",
        wiki_link="plaud/itr.md",
        linear_api_key="k",
        page_text="FULL TRANSCRIPT body",
    )

    assert refs and refs[0].identifier == "RA-9"

    anchor = grounding.anchor_from_text(captured["description"])
    assert anchor is not None, "No anchor found in ticket description"
    assert anchor["primary_source"] == "brain/plaud/itr.md"
    assert anchor["source_sha256"] == grounding._sha256_hex(b"FULL TRANSCRIPT body")


def test_ticket_description_still_contains_source_prose(monkeypatch):
    """Existing prose Source: line must still be present after retrofit."""
    captured = {}

    def fake_create_issue(*, api_key, title, description, team_id, project_id, priority):
        captured["description"] = description
        return pa.TicketRef(id="i1", identifier="RA-1", url="https://linear.app/x/RA-1")

    monkeypatch.setattr(pa, "create_linear_issue", fake_create_issue)

    action = pa.Action(title="Do thing", description="some desc", priority=2)
    pa.create_linear_tickets(
        actions=[action],
        team_id="t",
        project_id="p",
        wiki_link="plaud/test.md",
        linear_api_key="k",
        page_text="some page content",
    )

    desc = captured["description"]
    assert "Source:" in desc
    assert "test.md" in desc
    assert "some desc" in desc


def test_multiple_actions_share_one_anchor(monkeypatch):
    """All tickets filed from one page share the same anchor + source_sha256:
    the anchor is built once per page, before the per-action loop."""
    captured = []

    def fake_create_issue(*, api_key, title, description, team_id, project_id, priority):
        captured.append(description)
        return pa.TicketRef(id=f"i{len(captured)}", identifier=f"RA-{len(captured)}", url="")

    monkeypatch.setattr(pa, "create_linear_issue", fake_create_issue)

    actions = [
        pa.Action(title="A", description="do A", priority=3),
        pa.Action(title="B", description="do B", priority=2),
        pa.Action(title="C", description="do C", priority=1),
    ]
    refs = pa.create_linear_tickets(
        actions=actions,
        team_id="t",
        project_id="p",
        wiki_link="plaud/multi.md",
        linear_api_key="k",
        page_text="ONE PAGE for three actions",
    )

    assert len(refs) == 3
    anchors = [grounding.anchor_from_text(d) for d in captured]
    assert all(a is not None for a in anchors)
    # Same primary source and same content hash across every ticket.
    shas = {a["source_sha256"] for a in anchors}
    sources = {a["primary_source"] for a in anchors}
    assert shas == {grounding._sha256_hex(b"ONE PAGE for three actions")}
    assert sources == {"brain/plaud/multi.md"}


def test_create_linear_tickets_page_text_default_empty(monkeypatch):
    """Omitting page_text should still work (defaults to empty string)."""
    captured = {}

    def fake_create_issue(*, api_key, title, description, team_id, project_id, priority):
        captured["description"] = description
        return pa.TicketRef(id="i1", identifier="RA-2", url="")

    monkeypatch.setattr(pa, "create_linear_issue", fake_create_issue)

    action = pa.Action(title="T", description="D", priority=3)
    refs = pa.create_linear_tickets(
        actions=[action],
        team_id="t",
        project_id="p",
        wiki_link="plaud/other.md",
        linear_api_key="k",
        # page_text omitted — should default to ""
    )

    assert refs and refs[0].identifier == "RA-2"
    anchor = grounding.anchor_from_text(captured["description"])
    assert anchor is not None
    assert anchor["source_sha256"] == grounding._sha256_hex(b"")
