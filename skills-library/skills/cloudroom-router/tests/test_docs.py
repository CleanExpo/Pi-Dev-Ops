#!/usr/bin/env python3
"""The prose is instructions to agents, so the rules it states must agree with each other.
Run: python3 skills/cloudroom-router/tests/test_docs.py

Each check below is a rule the review found stated two ways, or missing, in these files.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DOC = (SKILL / "SKILL.md").read_text()
BRIEF = (SKILL / "references" / "worker-brief.md").read_text()
FORMAT = (SKILL / "references" / "ticket-format.md").read_text()
TEMPLATE = BRIEF[BRIEF.index("```text"):BRIEF.index("```", BRIEF.index("```text") + 7)]   # what a worker actually receives

TEAM_RULE = ("mode solo: no child threads. mode team: only its own Cloudroom child threads "
             "(`room-cli thread spawn --parent-self`), never harness subagents.")


class Docs(unittest.TestCase):
    def test_one_rule_for_worker_child_threads_in_both_files(self):
        self.assertIn(TEAM_RULE, DOC)
        self.assertIn(TEAM_RULE, TEMPLATE)
        self.assertNotIn("Do not start other threads or agents", BRIEF)
        self.assertNotIn("Starts other threads", DOC)

    def test_every_loop_delete_carries_yes(self):
        found = [ln for ln in (DOC + FORMAT + BRIEF).splitlines() if "loop delete" in ln]
        self.assertTrue(found, "no loop delete command is documented")
        for ln in found:
            self.assertIn("--yes", ln)

    def test_local_and_cloud_spawn_are_separate_commands_with_the_right_base(self):
        spawn = DOC[DOC.index("room-cli thread spawn --parent-self --project"):]
        local = spawn[:spawn.index("--json")]
        self.assertIn("--base-branch <local snapshot SHA>", local)
        self.assertNotIn("--machine cloud", local)
        self.assertIn("git commit", DOC)
        cloud = DOC[DOC.index("**Cloud worker**"):]
        cloud = " ".join(cloud[:cloud.index("\n\n")].split())
        self.assertIn("--machine cloud --base-branch tickets/<id>", cloud)
        self.assertIn("PUSHED branch name, not a SHA", cloud)
        self.assertIn("pr-release-gate", cloud)
        self.assertIn("a branch the router creates and owns", cloud)
        self.assertIn("pushed branch name", " ".join(BRIEF.split()))

    def test_queue_create_on_an_idle_thread_delivers_so_send_is_for_busy_targets_only(self):
        self.assertIn("IDLE thread it delivers at once", DOC)
        self.assertIn("HTTP 404", DOC)
        self.assertIn("only when the target is busy", " ".join(DOC.split()))
        fix_back = DOC[DOC.index("## 4. Fix-back"):DOC.index("## 5. Escalation")]
        code = fix_back[fix_back.index("```bash"):fix_back.index("```", fix_back.index("```bash") + 7)]
        self.assertIn("queue create", code)
        self.assertNotIn("queue send", code)

    def test_worker_brief_gives_the_absolute_ticket_path_as_fallback(self):
        self.assertIn("<ABSOLUTE TICKET FOLDER>", TEMPLATE)
        self.assertIn("--base-branch", BRIEF)

    def test_watchdog_loop_is_a_script_loop_with_no_agent_flags(self):
        cmd = DOC[DOC.index("room-cli loop create --project"):]
        cmd = cmd[:cmd.index("```")]
        self.assertIn("--script-file", cmd)
        self.assertIn("ROUTER_NOTIFY", cmd)
        for agent_flag in ("--prompt", "--provider", "--model", "--target-thread"):
            self.assertNotIn(agent_flag, cmd, "agent flags and script flags cannot be mixed in one loop")

    def test_one_writer_per_file_is_stated_the_same_way_everywhere(self):
        for text in (DOC, FORMAT):
            self.assertIn("APPROVED", text)
            self.assertIn("status", text)
        self.assertIn("HUMAN ONLY", DOC)
        self.assertIn("ROUTER ONLY", DOC)
        self.assertIn("GENERATED", DOC)
        self.assertIn("**the human only**", FORMAT)
        self.assertIn("**the router only**", FORMAT)
        self.assertIn("**generated**", FORMAT)
        self.assertIn("never runs `approve`", DOC)
        self.assertIn("never write or delete", FORMAT)

    def test_nothing_still_describes_the_two_writer_design(self):
        for text in (DOC, FORMAT, BRIEF):
            for dead in ("--human-approved", "under a lock", "flock", "re-reads `board.md`", "ROUTER_BOARD", "set --board"):
                self.assertNotIn(dead, text)
        self.assertNotIn("--board", DOC)

    def test_board_py_has_no_lock_or_hash_code_left(self):
        code = (SKILL / "scripts" / "board.py").read_text()
        for dead in ("fcntl", "flock", "sha256", "hashlib", "digest", "BoardChanged", "LockTimeout"):
            self.assertNotIn(dead, code, f"{dead}: a control that only existed for the two-writer design")

    def test_the_loop_reads_the_tickets_folder_not_board_md(self):
        cmd = DOC[DOC.index("room-cli loop create --project"):]
        cmd = cmd[:cmd.index("```")]
        self.assertIn("ROUTER_TICKETS", cmd)
        self.assertNotIn("board.md", cmd)

    def test_skill_is_short_enough_to_be_read(self):
        self.assertLess(len(DOC.splitlines()), 200)


if __name__ == "__main__":
    unittest.main(verbosity=1)
