"""Tests for swarm.pm_scoper — Senior PM Scoping Bot."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("LINEAR_API_KEY", "lin_test")


def _reload(state_path: Path | None = None):
    """Reload the module with a FRESH state path per call.

    Each test gets its own tempdir so persisted state from prior tests can't
    leak across (scoped_identifiers in particular).
    """
    if state_path is None:
        state_path = Path(tempfile.mkdtemp()) / "pm_scoper.jsonl"
    os.environ["TAO_PM_SCOPER_STATE"] = str(state_path)
    import importlib
    from swarm import pm_scoper as mod
    importlib.reload(mod)
    return mod


def _ticket(identifier="RA-9999", title="vague thing", description="please add it", team_id="team-1"):
    return {
        "id": f"issue-{identifier}",
        "identifier": identifier,
        "title": title,
        "url": f"https://linear.app/example/{identifier}",
        "createdAt": "2026-05-14T00:00:00Z",
        "description": description,
        "team": {"id": team_id, "key": identifier.split("-")[0], "name": "Test"},
        "labels": {"nodes": []},
        "assignee": None,
    }


class FetchAmbiguousTicketsTests(unittest.TestCase):
    def test_filter_by_label_and_backlog(self):
        mod = _reload()
        with patch.object(mod, "_linear_gql", return_value={"issues": {"nodes": [_ticket()]}}) as gql:
            result = mod.fetch_ambiguous_tickets(limit=3)
        # Verify GraphQL was called with the right label var
        called_vars = gql.call_args[0][1]
        self.assertEqual(called_vars["label"], "pi-dev:blocked-reason:ambiguous-spec")
        self.assertEqual(called_vars["limit"], 3)
        self.assertEqual(len(result), 1)


class RunCycleHappyPathTests(unittest.TestCase):
    def test_scopes_a_ticket_end_to_end(self):
        mod = _reload()
        ticket = _ticket(identifier="UNI-4242", title="add a settings page")
        with patch.object(mod, "fetch_ambiguous_tickets", return_value=[ticket]), \
             patch.object(mod, "_run_grounded_research",
                          return_value=("## Auto spec\n- AC1\n- AC2", 4)), \
             patch.object(mod, "post_comment", return_value="comment-id-1") as post_mock, \
             patch.object(mod, "_ensure_label", return_value="label-id"), \
             patch.object(mod, "_label_id_for", return_value="ambig-id"), \
             patch.object(mod, "update_labels") as labels_mock, \
             patch.object(mod, "should_run", return_value=True):
            r = mod.run_cycle(dry_run=False)

        self.assertEqual(r.tickets_seen, 1)
        self.assertEqual(r.tickets_scoped, 1)
        self.assertEqual(r.errors, [])
        post_mock.assert_called_once()
        labels_mock.assert_called_once()
        # The label update should ADD agent-ready + scoped-by-pm-bot, REMOVE ambiguous-spec
        call_kwargs = labels_mock.call_args.kwargs
        self.assertEqual(len(call_kwargs["add"]), 2)
        self.assertEqual(call_kwargs["remove"], ["ambig-id"])
        # ScopedTicket result has citations + summary
        self.assertEqual(r.scoped[0].identifier, "UNI-4242")
        self.assertEqual(r.scoped[0].citations_count, 4)

    def test_dry_run_no_writes(self):
        mod = _reload()
        ticket = _ticket()
        with patch.object(mod, "fetch_ambiguous_tickets", return_value=[ticket]), \
             patch.object(mod, "_run_grounded_research", return_value=("spec", 2)), \
             patch.object(mod, "post_comment") as post_mock, \
             patch.object(mod, "update_labels") as labels_mock, \
             patch.object(mod, "should_run", return_value=True):
            r = mod.run_cycle(dry_run=True)
        self.assertEqual(r.tickets_scoped, 1)
        # In dry run, NO mutations happen
        post_mock.assert_not_called()
        labels_mock.assert_not_called()


class CycleCooldownTests(unittest.TestCase):
    def test_returns_skipped_when_cooldown_active(self):
        mod = _reload()
        with patch.object(mod, "should_run", return_value=False):
            r = mod.run_cycle(dry_run=False)
        self.assertEqual(r.skipped_reason, "cycle-cooldown")
        self.assertEqual(r.tickets_seen, 0)


class DeDupePrevScopedTests(unittest.TestCase):
    def test_skips_tickets_already_scoped_in_prior_run(self):
        mod = _reload()
        # Write state showing UNI-4242 was already scoped
        state_path = Path(mod.STATE_PATH)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "last_run_ts": 0, "scoped_identifiers": ["UNI-4242"],
        }) + "\n")
        ticket = _ticket(identifier="UNI-4242")
        with patch.object(mod, "fetch_ambiguous_tickets", return_value=[ticket]), \
             patch.object(mod, "_run_grounded_research") as research_mock, \
             patch.object(mod, "should_run", return_value=True):
            r = mod.run_cycle(dry_run=False)
        self.assertEqual(r.tickets_seen, 1)
        self.assertEqual(r.tickets_scoped, 0)
        research_mock.assert_not_called()


class GroundedResearchFallbackTests(unittest.TestCase):
    def test_template_fallback_when_gemini_unavailable(self):
        mod = _reload()
        ticket = _ticket()
        # Simulate gemini_research import failing
        import sys
        with patch.dict(sys.modules, {"swarm.research.gemini_research": None}):
            summary, count = mod._run_grounded_research(ticket)
        self.assertIn("template fallback", summary.lower())
        self.assertEqual(count, 0)


class PerTicketErrorContainmentTests(unittest.TestCase):
    def test_one_bad_ticket_does_not_block_the_others(self):
        mod = _reload()
        t_bad = _ticket(identifier="BAD-1")
        t_good = _ticket(identifier="GOOD-1")
        # The "bad" ticket fails research
        def fake_research(ticket):
            if ticket["identifier"] == "BAD-1":
                raise RuntimeError("boom")
            return ("spec", 1)
        with patch.object(mod, "fetch_ambiguous_tickets", return_value=[t_bad, t_good]), \
             patch.object(mod, "_run_grounded_research", side_effect=fake_research), \
             patch.object(mod, "post_comment", return_value="c1"), \
             patch.object(mod, "_ensure_label", return_value="lid"), \
             patch.object(mod, "_label_id_for", return_value="aid"), \
             patch.object(mod, "update_labels"), \
             patch.object(mod, "should_run", return_value=True):
            r = mod.run_cycle(dry_run=False)
        self.assertEqual(r.tickets_seen, 2)
        self.assertEqual(r.tickets_scoped, 1)
        self.assertEqual(len(r.errors), 1)
        self.assertIn("BAD-1", r.errors[0])


if __name__ == "__main__":
    unittest.main()
