"""Tests for swarm.history_parser — RA-6472 repo history parser."""
from __future__ import annotations

import unittest

from swarm.history_parser import (
    RepoHistoryMap,
    classify_issue,
    classify_pr,
    is_pull_request,
    parse_repo,
    render_map,
)


class ClassifyIssueTests(unittest.TestCase):
    def test_closed_completed_is_implemented(self):
        self.assertEqual(
            classify_issue({"state": "closed", "state_reason": "completed"}),
            "implemented",
        )

    def test_closed_not_planned_is_abandoned(self):
        self.assertEqual(
            classify_issue({"state": "closed", "state_reason": "not_planned"}),
            "abandoned",
        )

    def test_closed_no_reason_defaults_implemented(self):
        self.assertEqual(classify_issue({"state": "closed"}), "implemented")

    def test_open_assigned_is_started(self):
        self.assertEqual(
            classify_issue({"state": "open", "assignee": {"login": "x"}}),
            "started",
        )
        self.assertEqual(
            classify_issue({"state": "open", "assignees": [{"login": "x"}]}),
            "started",
        )

    def test_open_unassigned_is_never_built(self):
        self.assertEqual(
            classify_issue({"state": "open", "assignees": []}), "never_built"
        )


class ClassifyPrTests(unittest.TestCase):
    def test_merged_is_implemented(self):
        self.assertEqual(classify_pr({"state": "closed", "merged_at": "2026-01-01T00:00:00Z"}), "implemented")

    def test_open_is_started(self):
        self.assertEqual(classify_pr({"state": "open", "merged_at": None}), "started")

    def test_closed_unmerged_is_abandoned(self):
        self.assertEqual(classify_pr({"state": "closed", "merged_at": None}), "abandoned")


class IsPullRequestTests(unittest.TestCase):
    def test_detects_pr_shaped_issue(self):
        self.assertTrue(is_pull_request({"number": 1, "pull_request": {"url": "x"}}))
        self.assertFalse(is_pull_request({"number": 2}))


class ParseRepoTests(unittest.TestCase):
    def test_parse_repo_filters_prs_from_issues_and_classifies(self):
        issues_page = [
            {"number": 1, "title": "done", "state": "closed",
             "state_reason": "completed", "html_url": "u1", "updated_at": "t1"},
            {"number": 2, "title": "wontfix", "state": "closed",
             "state_reason": "not_planned", "html_url": "u2", "updated_at": "t2"},
            {"number": 3, "title": "idea", "state": "open", "assignees": [],
             "html_url": "u3", "updated_at": "t3"},
            {"number": 4, "title": "a pr leaked into issues", "state": "open",
             "pull_request": {"url": "p"}, "html_url": "u4", "updated_at": "t4"},
        ]
        pulls_page = [
            {"number": 10, "title": "merged pr", "state": "closed",
             "merged_at": "2026-01-01T00:00:00Z", "html_url": "p10", "updated_at": "t10"},
            {"number": 11, "title": "open pr", "state": "open", "merged_at": None,
             "html_url": "p11", "updated_at": "t11"},
        ]

        def fake_gh_get(path, *, params=None, token=""):
            page = (params or {}).get("page", 1)
            if page != 1:
                return []
            return issues_page if path.endswith("/issues") else pulls_page

        m = parse_repo("CleanExpo/CCW-CRM", gh_get=fake_gh_get)
        self.assertIsInstance(m, RepoHistoryMap)
        # PR #4 leaked into the issues feed must be filtered out; 3 issues + 2 pulls.
        self.assertEqual(len(m.items), 5)
        counts = m.counts()
        self.assertEqual(counts["implemented"], 2)  # issue #1 + merged PR #10
        self.assertEqual(counts["abandoned"], 1)    # issue #2
        self.assertEqual(counts["never_built"], 1)  # issue #3
        self.assertEqual(counts["started"], 1)      # open PR #11

    def test_render_map_lists_all_statuses(self):
        m = parse_repo("owner/repo", gh_get=lambda *a, **k: [])
        out = render_map(m)
        self.assertIn("owner/repo", out)
        for status in ("implemented", "started", "abandoned", "never_built"):
            self.assertIn(status, out)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
