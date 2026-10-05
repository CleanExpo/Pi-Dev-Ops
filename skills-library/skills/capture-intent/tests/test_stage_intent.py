#!/usr/bin/env python3
"""stage_intent.py: an accepted intent reaches /plan-ceo-review, and nothing else does.

Every refusal case asserts that NO file was left behind: a refused intent that still
landed in ~/.gstack would be read by the CEO review as if it had been accepted.

    python3 skills/capture-intent/tests/test_stage_intent.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "stage_intent.py"
FIXTURES = HERE / "fixtures"
GOOD = (FIXTURES / "accepted-intent.md").read_text()
LOOKUP = FIXTURES / "ceo-lookup.md"
PINNED = Path(os.path.expanduser("~/.claude/skills/gstack-plan-ceo-review/SKILL.md")).resolve()


class StageIntent(unittest.TestCase):
    def setUp(self):
        # Space-free base: an ambient TMPDIR with a space would break the upstream lookup
        # for reasons unrelated to the case under test (that case has its own test).
        self.tmp = tempfile.TemporaryDirectory(dir="/tmp" if os.path.isdir("/tmp") else None)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.repo = root / "demo-repo"
        self.repo.mkdir()
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", "-b", "feat/x"], cwd=self.repo, check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, text: str, lookup: Path = LOOKUP, home: Path | None = None):
        src = Path(self.tmp.name) / "intent.md"
        src.write_text(text)
        env = {**os.environ, "HOME": str(home or self.home)}
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(src), "--repo", str(self.repo), "--lookup-from", str(lookup)],
            capture_output=True, text=True, env=env,
        )

    def staged(self):
        return list((self.home / ".gstack").rglob("*-design-*.md")) if (self.home / ".gstack").exists() else []

    def assertRefused(self, r, why: str):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(why, r.stderr)
        self.assertEqual(self.staged(), [], "a refused intent must leave no design doc behind")

    # --- positive -----------------------------------------------------------
    def test_accepted_intent_is_what_the_ceo_lookup_finds(self):
        r = self.stage(GOOD)
        self.assertEqual(r.returncode, 0, r.stderr)
        [doc] = self.staged()
        self.assertEqual(doc.parent, self.home / ".gstack/projects/demo-repo")
        self.assertRegex(doc.name, r"-feat-x-design-\d{8}-\d{6}\.md$")
        self.assertIn(f"Design doc found: {doc}", r.stdout)
        self.assertIn("## Constraints", doc.read_text())

    # --- negative controls: each must refuse --------------------------------
    def test_draft_status_is_refused(self):
        self.assertRefused(self.stage(GOOD.replace("status: accepted", "status: draft")), "not `status: accepted`")

    def test_no_frontmatter_is_refused(self):
        body = GOOD.split("---\n", 2)[2]
        self.assertRefused(self.stage(body), "not `status: accepted`")

    def test_missing_section_is_refused(self):
        self.assertRefused(self.stage(GOOD.replace("## Constraints", "## Limits")), "missing section `## Constraints`")

    def test_empty_section_is_refused(self):
        text = GOOD.replace("Do insurers expose a status we can read, or do we only know what we sent?\n", "")
        self.assertRefused(self.stage(text), "section `## Open questions` is empty")

    def test_missing_title_is_refused(self):
        self.assertRefused(self.stage(GOOD.replace("# Intent:", "# Idea:")), "missing title")

    def test_newer_repo_design_doc_shadowing_is_refused(self):
        designs = self.repo / "docs" / "designs"
        designs.mkdir(parents=True)
        shadow = designs / "old.md"
        shadow.write_text("# someone else's design\n")
        future = time.time() + 3600
        os.utime(shadow, (future, future))
        self.assertRefused(self.stage(GOOD), "shadows the staged intent")

    def test_any_code_fence_is_refused_at_any_indent(self):
        # Reviewer-planted bypasses (cursor, 2cedfaf4 and 63d7113f): the real Open questions
        # section is missing and its heading sits inside a fence - column 0, indented 1-3
        # spaces, tab-indented, backtick or tilde, closed or not. Any fence is refused.
        head, _ = GOOD.split("## Open questions")
        for indent in ("", " ", "   ", "\t"):
            for mark in ("```", "~~~"):
                for close in (True, False):
                    with self.subTest(indent=repr(indent), mark=mark, closed=close):
                        tail = f"{indent}{mark}\n" if close else ""
                        text = head + f"{indent}{mark}\n## Open questions\nhidden\n{tail}"
                        self.assertRefused(self.stage(text), "code blocks are not allowed")

    def test_any_raw_html_is_refused(self):
        # Reviewer-planted bypasses (cursor, 2e603fc2 and 7c9bf063): a heading hidden in
        # <pre>, <!-- -->, <code>, <textarea>, <script>, <div> or an unclosed comment. Each
        # allow-listed fix left a sibling gap, so any raw HTML now fails closed.
        head, _ = GOOD.split("## Open questions")
        for wrapper in ("<pre>", "<!--", "<code>", "<textarea>", "<script>", "<div>", "</div>"):
            with self.subTest(wrapper=wrapper):
                text = head + f"{wrapper}\n## Open questions\nhidden\n"
                self.assertRefused(self.stage(text), "raw HTML is not allowed")

    def test_angle_brackets_and_autolinks_in_plain_prose_are_allowed(self):
        # Fail-closed must not refuse ordinary text or CommonMark autolinks. Each phrase is
        # staged on its own so one wrongly refused phrase cannot hide behind another
        # (round-5 P1: "a < b" was refused as HTML).
        for phrase in ("a < b", "x < y", "< ten minutes", "< 10 minutes", "x<5 per day",
                       "a -> b", "<https://example.com/claims>", "<ftp://files.example.com/x>",
                       "<ops@example.com>", "Notify <customer> by SMS", "Must cost <AUD 500",
                       "use <b>bold</b> sparingly"):
            with self.subTest(phrase=phrase):
                text = GOOD.replace("Each call costs about ten minutes.", f"Note: {phrase}.")
                r = self.stage(text)
                self.assertEqual(r.returncode, 0, f"{phrase!r} wrongly refused: {r.stderr}")
                for doc in self.staged():
                    doc.unlink()

    def test_sections_only_inside_frontmatter_are_refused(self):
        # Reviewer-planted bypass (cursor, e7e4647b): all five headings inside the YAML
        # block, body holding only the title.
        fm_end = GOOD.index("\n---\n", 4)
        fm = GOOD[:fm_end]
        sections = GOOD[GOOD.index("## Problem"):]
        text = fm + "\n" + sections + "---\n# Intent: title only outside\n"
        self.assertRefused(self.stage(text), "missing section `## Problem`")

    def test_html_at_line_start_after_indent_is_refused(self):
        # Up to 3 spaces of indent still opens an HTML block that can swallow a heading.
        head, _ = GOOD.split("## Open questions")
        for indent in (" ", "   "):
            with self.subTest(indent=repr(indent)):
                text = head + f"{indent}<div>\n## Open questions\nhidden\n"
                self.assertRefused(self.stage(text), "raw HTML is not allowed")

    def test_quoted_accepted_status_is_allowed(self):
        for quoted in ('"accepted"', "'accepted'"):
            with self.subTest(status=quoted):
                r = self.stage(GOOD.replace("status: accepted", f"status: {quoted}"))
                self.assertEqual(r.returncode, 0, r.stderr)
                for doc in self.staged():
                    doc.unlink()

    def test_second_status_line_is_refused(self):
        text = GOOD.replace("status: accepted\n", "status: accepted\nstatus: draft\n")
        self.assertRefused(self.stage(text), "exactly one status line")

    def test_vacuous_section_markers_are_refused(self):
        body = "Do insurers expose a status we can read, or do we only know what we sent?"
        for filler in (".", "---", "***", "[//]: # (nothing)"):
            with self.subTest(filler=filler):
                self.assertRefused(self.stage(GOOD.replace(body, filler)), "section `## Open questions` is empty")

    def test_invisible_only_section_is_refused(self):
        # Reviewer P2 (cursor, 63d7113f): a zero-width space or &nbsp; is not content.
        body = "Do insurers expose a status we can read, or do we only know what we sent?"
        for filler in ("​", "&nbsp;", " "):
            with self.subTest(filler=repr(filler)):
                self.assertRefused(self.stage(GOOD.replace(body, filler)), "section `## Open questions` is empty")

    def test_empty_author_or_created_value_is_refused(self):
        # Reviewer-planted bypass (cursor, 2e603fc2): a bare key borrowed the next line.
        for field in ("author", "created"):
            for bare in (f"{field}:", f"{field}: "):
                with self.subTest(line=bare):
                    text = "\n".join(bare if l.startswith(f"{field}:") else l for l in GOOD.splitlines()) + "\n"
                    self.assertRefused(self.stage(text), f"missing `{field}:`")

    def test_missing_created_is_refused(self):
        text = "\n".join(l for l in GOOD.splitlines() if not l.startswith("created:")) + "\n"
        self.assertRefused(self.stage(text), "missing `created:`")

    def test_missing_author_is_refused(self):
        text = "\n".join(l for l in GOOD.splitlines() if not l.startswith("author:")) + "\n"
        self.assertRefused(self.stage(text), "missing `author:`")

    def test_home_with_a_space_is_honest_either_way(self):
        # Whether the pinned lookup sees a HOME with a space depends on the shell: macOS
        # /bin/bash 3.2 word-splits `~/.gstack/projects/$SLUG/...` at the space; bash 5 (CI
        # Linux) does not. Both outcomes are honest; what must never happen is a staged file
        # the lookup cannot see, or a refusal that leaves files behind.
        spaced = Path(self.tmp.name) / "user home"
        spaced.mkdir()
        r = self.stage(GOOD, home=spaced)
        docs = list((spaced / ".gstack").rglob("*-design-*.md")) if (spaced / ".gstack").exists() else []
        if r.returncode == 0:
            [doc] = docs
            self.assertIn(f"Design doc found: {doc}", r.stdout)
        else:
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("cannot see files under", r.stderr)
            self.assertNotIn("shadows", r.stderr)
            self.assertEqual(docs, [])
            self.assertFalse((spaced / ".gstack/projects/demo-repo").exists(), "empty project dir left behind")

    def test_lookup_snippet_drift_is_refused(self):
        drifted = Path(self.tmp.name) / "drifted.md"
        drifted.write_text("# plan-ceo-review\nno lookup here\n")
        self.assertRefused(self.stage(GOOD, lookup=drifted), "lookup snippet not found")


@unittest.skipUnless(PINNED.exists(), "pinned gstack not installed on this machine")
class FixtureMatchesPinnedUpstream(unittest.TestCase):
    def test_fixture_snippet_is_the_pinned_one(self):
        # If gstack's lookup changes, the fixture (and this script) must be re-checked.
        self.assertIn(LOOKUP.read_text().strip(), PINNED.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
