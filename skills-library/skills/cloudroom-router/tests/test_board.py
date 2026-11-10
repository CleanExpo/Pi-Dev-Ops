#!/usr/bin/env python3
"""Tests for scripts/board.py. Run: python3 skills/cloudroom-router/tests/test_board.py

One writer per file: the human owns prd.md, eval.md and APPROVED; the router owns each ticket's
status file; board.md is a generated view. The lost-update tests below make the human act at
every moment of a router write, and the human's file must always survive.
mutate_router.py proves each guard here goes red when its code is broken.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
BOARD = HERE.parent / "scripts" / "board.py"
sys.path.insert(0, str(BOARD.parent))
import board as bm  # noqa: E402  (in-process access for the interleaving tests)

# id, slug, mode, runs, approved, status line
GOOD = [
    ("001", "schema", "solo", "alongside", True, "done worker=thr_a"),
    ("002", "api", "solo", "after 001: needs the schema", True, None),
    ("003", "ui", "team", "after 001, 002: needs the api", True, None),
    ("004", "docs", "solo", "alongside", False, None),
    ("005", "other", "solo", "alongside", True, None),
]


def make(spec=GOOD, prd_extra: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="router-board-")) / "tickets"
    root.mkdir()
    for tid, slug, mode, runs, approved, status in spec:
        d = root / f"{tid}-{slug}"
        d.mkdir()
        (d / "prd.md").write_text(f"---\nmode: {mode}\nruns: {runs}\n---\n# prd\nwhat\n")
        (d / "eval.md").write_text("# eval\nhow\n")
        if approved:
            (d / "APPROVED").write_text("approved by the human\n")
        if status:
            (d / "status").write_text(status + "\n")
    return root


def run(root: Path, *args: str):
    p = subprocess.run([sys.executable, str(BOARD), "--tickets", str(root), *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def changed(before: dict, after: dict) -> set[str]:
    return {k for k in set(before) | set(after) if before.get(k) != after.get(k)}


def status_of(root: Path, folder: str) -> str:
    return (root / folder / "status").read_text()


class Validate(unittest.TestCase):
    def test_clean_board_passes(self):
        self.assertEqual(run(make(), "validate"), (0, "", ""))

    def test_missing_or_blank_prd_and_eval(self):
        r = make()
        (r / "002-api" / "eval.md").unlink()
        (r / "003-ui" / "prd.md").write_text("   \n")
        rc, out, _ = run(r, "validate")
        self.assertEqual(rc, 1)
        self.assertIn("002-api/eval.md is missing or empty", out)
        self.assertIn("003-ui/prd.md is missing or empty", out)

    def test_prd_without_front_matter(self):
        r = make()
        (r / "002-api" / "prd.md").write_text("# prd with no front matter\n")
        rc, out, _ = run(r, "validate")
        self.assertEqual(rc, 1)
        self.assertIn("no front matter", out)

    def test_duplicate_id(self):
        r = make(GOOD + [("002", "again", "solo", "alongside", True, None)])
        rc, out, _ = run(r, "validate")
        self.assertEqual(rc, 1)
        self.assertIn("002: duplicate id", out)

    def test_dependency_that_does_not_exist(self):
        rc, out, _ = run(make([("001", "a", "solo", "after 009: because", True, None)]), "validate")
        self.assertEqual(rc, 1)
        self.assertIn("depends on 009, which is not on the board", out)

    def test_cycle_is_found(self):
        r = make([("001", "a", "solo", "after 002: x", True, None), ("002", "b", "solo", "after 003: x", True, None),
                  ("003", "c", "solo", "after 001: x", True, None)])
        rc, out, _ = run(r, "validate")
        self.assertEqual(rc, 1)
        self.assertIn("dependency cycle", out)

    def test_self_dependency(self):
        rc, out, _ = run(make([("001", "a", "solo", "after 001: x", True, None)]), "validate")
        self.assertEqual(rc, 1)
        self.assertIn("depends on itself", out)

    def test_bad_mode_runs_and_folder_name(self):
        r = make([("001", "a", "duo", "alongside", True, None), ("002", "b", "solo", "after 001", True, None)])
        (r / "003_oops").mkdir()
        (r / "7-short").mkdir()
        rc, out, _ = run(r, "validate")
        self.assertEqual(rc, 1)
        self.assertIn("001: mode 'duo'", out)
        self.assertIn("002: runs 'after 001'", out)
        self.assertIn("7-short: folder must be", out)

    def test_status_file_must_be_one_clean_line(self):
        for bad in ("started", "doing", "doing worker=", "ready extra", "doing worker=thr_a\nreview worker=thr_a", "blocked worker=thr_a"):
            with self.subTest(bad=bad):
                r = make([("001", "a", "solo", "alongside", True, None)])
                (r / "001-a" / "status").write_text(bad + "\n")
                rc, out, _ = run(r, "validate")
                self.assertEqual(rc, 1, out)

    def test_status_without_approval_is_invalid(self):
        r = make([("001", "a", "solo", "alongside", False, "ready")])
        rc, out, _ = run(r, "validate")
        self.assertEqual(rc, 1)
        self.assertIn("no APPROVED", out)

    def test_unreadable_or_empty_tickets_folder_is_unknown_not_clean(self):
        d = Path(tempfile.mkdtemp())
        for args in (["validate"], ["next"], ["render"]):
            rc, out, err = run(d / "missing", *args)
            self.assertEqual((rc, out), (2, ""), args)
            self.assertIn("UNKNOWN", err)
            rc, out, err = run(d, *args)           # exists, but holds no tickets
            self.assertEqual((rc, out), (2, ""), args)
            self.assertIn("UNKNOWN", err)


class Next(unittest.TestCase):
    def test_only_approved_with_all_deps_done(self):
        # 002 (dep 001 done) and 005 qualify; 003 waits on 002; 004 is a draft; 001 is done.
        self.assertEqual(run(make(), "next")[1], "002 api solo\n005 other solo\n")

    def test_approving_is_what_makes_a_draft_ready(self):
        r = make()
        self.assertNotIn("004", run(r, "next")[1])
        (r / "004-docs" / "APPROVED").write_text("")
        self.assertIn("004 docs solo", run(r, "next")[1])

    def test_doing_and_blocked_are_not_offered(self):
        r = make()
        (r / "002-api" / "status").write_text("doing worker=thr_w\n")
        (r / "005-other" / "status").write_text("blocked was=ready\n")
        self.assertEqual(run(r, "next")[1], "")

    def test_cap_counts_workers_already_doing(self):
        r = make()
        self.assertEqual(run(r, "next", "--cap", "1")[1], "002 api solo\n")
        (r / "002-api" / "status").write_text("doing worker=thr_w\n")
        self.assertEqual(run(r, "next", "--cap", "1"), (0, "", ""))

    def test_json(self):
        rc, out, _ = run(make(), "next", "--json")
        self.assertEqual(json.loads(out), [{"id": "002", "slug": "api", "mode": "solo"}, {"id": "005", "slug": "other", "mode": "solo"}])

    def test_invalid_board_dispatches_nothing(self):
        r = make()
        (r / "005-other" / "eval.md").unlink()
        rc, out, err = run(r, "next")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("REFUSED", err)

    def test_a_human_edit_to_board_md_never_changes_next(self):
        r = make()
        expected = run(r, "next")[1]
        view = r / "board.md"
        for text in ("| 004 | docs | ready | solo | alongside | |\n", "| 002 | api | done | solo | alongside | thr_x |\n",
                     "garbage that is not a table\n", ""):
            view.write_text(text)
            self.assertEqual(run(r, "next")[1], expected, text)
        view.unlink()
        self.assertEqual(run(r, "next")[1], expected)
        self.assertEqual(run(r, "validate")[0], 0)


class SetStatus(unittest.TestCase):
    def test_dispatch_writes_only_that_tickets_status_and_the_view(self):
        r = make()
        before = snapshot(r)
        rc, out, _ = run(r, "set", "002", "doing", "--worker", "thr_w9")
        self.assertEqual((rc, out), (0, "002: ready -> doing\n"))
        self.assertEqual(status_of(r, "002-api"), "doing worker=thr_w9\n")
        self.assertEqual(changed(before, snapshot(r)), {"002-api/status", "board.md"})
        self.assertEqual(run(r, "validate")[0], 0)
        self.assertEqual([p.name for p in r.rglob(".tmp-*")], [], "temp file left behind")

    def test_a_draft_cannot_be_started_or_blocked_by_the_router(self):
        r = make()
        before = snapshot(r)
        for dst in ("ready", "doing", "blocked", "review", "done"):
            rc, _, err = run(r, "set", "004", dst, "--worker", "thr_w")
            self.assertEqual(rc, 1, dst)
            self.assertIn("not approved", err)
        self.assertEqual(snapshot(r), before)

    def test_doing_needs_worker(self):
        rc, _, err = run(make(), "set", "005", "doing")
        self.assertEqual(rc, 1)
        self.assertIn("--worker", err)

    def test_doing_refused_while_dependency_not_done(self):
        r = make()
        before = snapshot(r)
        rc, _, err = run(r, "set", "003", "doing", "--worker", "thr_w")
        self.assertEqual(rc, 1)
        self.assertIn("002", err)
        self.assertEqual(snapshot(r), before)

    def test_done_only_from_review_and_fix_back_keeps_the_worker(self):
        r = make()
        self.assertEqual(run(r, "set", "005", "done")[0], 1)
        self.assertEqual(run(r, "set", "005", "doing", "--worker", "thr_w")[0], 0)
        self.assertEqual(run(r, "set", "005", "done")[0], 1)
        self.assertEqual(run(r, "set", "005", "review")[0], 0)
        self.assertEqual(run(r, "set", "005", "doing")[0], 0)
        self.assertEqual(status_of(r, "005-other"), "doing worker=thr_w\n")
        self.assertEqual(run(r, "set", "005", "review")[0], 0)
        self.assertEqual(run(r, "set", "005", "done")[0], 0)

    def test_reassigning_a_lost_worker_keeps_the_ticket_doing(self):
        r = make()
        run(r, "set", "005", "doing", "--worker", "thr_old")
        rc, out, _ = run(r, "set", "005", "doing", "--worker", "thr_new")
        self.assertEqual((rc, out), (0, "005: doing -> doing\n"))
        self.assertEqual(status_of(r, "005-other"), "doing worker=thr_new\n")

    def test_blocked_remembers_where_it_came_from(self):
        r = make()
        self.assertEqual(run(r, "set", "005", "doing", "--worker", "thr_w")[0], 0)
        self.assertEqual(run(r, "set", "005", "blocked")[0], 0)
        self.assertEqual(status_of(r, "005-other"), "blocked worker=thr_w was=doing\n")
        self.assertEqual(run(r, "validate")[0], 0)
        self.assertEqual(run(r, "next")[1], "002 api solo\n", "a blocked ticket is never offered")
        self.assertEqual(run(r, "set", "005", "doing")[0], 0)
        self.assertEqual(status_of(r, "005-other"), "doing worker=thr_w\n")

    def test_unknown_ticket_and_status(self):
        r = make()
        rc, _, err = run(r, "set", "099", "doing", "--worker", "t")
        self.assertEqual(rc, 2)
        self.assertIn("UNKNOWN", err)
        self.assertEqual(run(r, "set", "005", "finished")[0], 1)

    def test_bad_worker_id_refused(self):
        self.assertEqual(run(make(), "set", "005", "doing", "--worker", "a | b")[0], 1)

    def test_set_validates_the_whole_board_first(self):
        r = make([("001", "a", "solo", "alongside", True, None), ("002", "b", "solo", "after typo", True, None)])
        before = snapshot(r)
        rc, _, err = run(r, "set", "001", "doing", "--worker", "thr_w")
        self.assertEqual(rc, 1)
        self.assertIn("002: runs 'after typo'", err)
        self.assertEqual(snapshot(r), before)

    def test_review_requires_a_worker_like_doing(self):
        r = make([("001", "a", "solo", "alongside", True, "doing worker=thr_w")])
        board = bm.load(r)
        board.get("001")["worker"] = ""        # in memory: bypasses validate on purpose
        with self.assertRaises(ValueError) as cm:
            bm.set_status(board, "001", "review", None)
        self.assertIn("--worker", str(cm.exception))
        self.assertEqual(run(r, "set", "001", "review")[0], 0)


STATES = {
    "draft": (False, None), "ready": (True, None), "ready-file": (True, "ready"),
    "doing": (True, "doing worker=thr_w"), "review": (True, "review worker=thr_w"), "done": (True, "done worker=thr_w"),
    "blocked(ready)": (True, "blocked was=ready"), "blocked(doing)": (True, "blocked worker=thr_w was=doing"),
    "blocked(review)": (True, "blocked worker=thr_w was=review"),
}
ALLOWED = {
    ("ready", "doing"), ("ready-file", "doing"), ("doing", "review"), ("review", "doing"), ("review", "done"), ("doing", "doing"),
    ("ready", "blocked"), ("ready-file", "blocked"), ("doing", "blocked"), ("review", "blocked"),
    ("blocked(ready)", "ready"), ("blocked(doing)", "doing"), ("blocked(review)", "review"),
}


class TransitionTable(unittest.TestCase):
    def test_every_pair_is_decided_by_the_table_alone(self):
        for src, (approved, line) in STATES.items():
            for dst in bm.STATUSES:
                with self.subTest(src=src, dst=dst):
                    r = make([("001", "only", "solo", "alongside", approved, line)])
                    before = snapshot(r)
                    args = ["set", "001", dst] + (["--worker", "thr_w"] if dst in ("doing", "review") else [])
                    rc, _, err = run(r, *args)
                    if (src, dst) in ALLOWED:
                        self.assertEqual(rc, 0, err)
                    else:
                        self.assertEqual(rc, 1, f"{src} -> {dst} must be refused")
                        self.assertEqual(snapshot(r), before)


class Approve(unittest.TestCase):
    def test_approve_creates_only_the_marker(self):
        r = make()
        before = snapshot(r)
        rc, out, _ = run(r, "approve", "004")
        self.assertEqual((rc, out), (0, "004: approved\n"))
        self.assertEqual(changed(before, snapshot(r)), {"004-docs/APPROVED"})
        self.assertIn("004 docs solo", run(r, "next")[1])

    def test_approve_never_overwrites_the_humans_marker(self):
        r = make()
        marker = r / "002-api" / "APPROVED"
        marker.write_text("the human wrote this\n")
        st = marker.stat()
        rc, out, _ = run(r, "approve", "002")
        self.assertEqual((rc, out), (0, "002: already approved\n"))
        self.assertEqual(marker.read_text(), "the human wrote this\n")
        self.assertEqual((marker.stat().st_ino, marker.stat().st_mtime_ns), (st.st_ino, st.st_mtime_ns))

    def test_approve_unknown_ticket(self):
        rc, _, err = run(make(), "approve", "099")
        self.assertEqual(rc, 2)
        self.assertIn("UNKNOWN", err)

    def test_no_other_command_touches_an_approval(self):
        r = make()
        markers = {p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in r.rglob("APPROVED")}
        for args in (["validate"], ["next"], ["render"], ["set", "005", "doing", "--worker", "thr_w"], ["set", "005", "review"],
                     ["set", "005", "done"], ["set", "002", "doing", "--worker", "thr_x"], ["set", "002", "blocked"]):
            run(r, *args)
        after = {p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in r.rglob("APPROVED")}
        self.assertEqual(after, markers)

    def test_static_only_approve_creates_approved_and_nothing_deletes_it(self):
        tree = ast.parse(BOARD.read_text())
        mutating = {"os.open", "os.unlink", "os.remove", "os.replace", "os.rename", "os.rmdir", "os.fdopen", "open",
                    "shutil.rmtree", "shutil.move", "shutil.copy", "shutil.copyfile"}
        mutating_methods = {"write_text", "write_bytes", "unlink", "rename", "replace", "touch", "rmdir", "mkdir", "symlink_to"}
        found: dict[str, set[str]] = {}
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            for call in (c for c in ast.walk(fn) if isinstance(c, ast.Call)):
                f = call.func
                name = ast.unparse(f)
                if name in mutating or (isinstance(f, ast.Attribute) and f.attr in mutating_methods):
                    found.setdefault(fn.name, set()).add(name)
        self.assertEqual(found, {"_write_atomic": {"os.fdopen", "os.replace", "os.unlink"},
                                 "approve": {"os.open", "os.fdopen"}})
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        # the only unlink removes the temp file, never a ticket file
        unlink = [c for c in ast.walk(fns["_write_atomic"]) if isinstance(c, ast.Call) and ast.unparse(c.func) == "os.unlink"]
        self.assertEqual([ast.unparse(c.args[0]) for c in unlink], ["tmp"])
        # the only writes are the status file, the view, and approve's exclusive create
        callers = {fn.name for fn in fns.values() for c in ast.walk(fn)
                   if isinstance(c, ast.Call) and ast.unparse(c.func) == "_write_atomic"}
        self.assertEqual(callers, {"write_status", "write_view"})
        for fn, target in (("write_status", "STATUS"), ("write_view", "VIEW")):
            targets = [ast.unparse(c.args[0]) for c in ast.walk(fns[fn]) if isinstance(c, ast.Call) and ast.unparse(c.func) == "_write_atomic"]
            self.assertEqual(len(targets), 1)
            self.assertIn(target, targets[0])
            self.assertNotIn("APPROVED", targets[0])
        flags = ast.unparse([c for c in ast.walk(fns["approve"]) if isinstance(c, ast.Call) and ast.unparse(c.func) == "os.open"][0].args[1])
        self.assertIn("O_EXCL", flags)
        self.assertIn("O_CREAT", flags)
        self.assertNotIn("O_TRUNC", flags)


class View(unittest.TestCase):
    def test_render_is_a_marked_generated_view_of_the_real_state(self):
        r = make()
        self.assertEqual(run(r, "render"), (0, "", ""))
        text = (r / "board.md").read_text()
        self.assertIn("generated by board.py render - do not edit", text)
        self.assertIn("| 001 | schema | done | solo | alongside | thr_a |", text)
        self.assertIn("| 004 | docs | draft |", text)
        self.assertIn("| 002 | api | ready |", text)
        run(r, "set", "005", "doing", "--worker", "thr_z")
        run(r, "set", "005", "blocked")
        self.assertIn("| 005 | other | blocked (was doing) | solo | alongside | thr_z |", (r / "board.md").read_text())

    def test_render_overwrites_a_human_edit_without_reading_it(self):
        r = make()
        (r / "board.md").write_text("| 004 | docs | ready | solo | alongside | |\n")
        run(r, "render")
        self.assertIn("| 004 | docs | draft |", (r / "board.md").read_text())
        self.assertNotIn("004-docs/status", snapshot(r))


class LostUpdate(unittest.TestCase):
    """The class that failed twice: a human acting while the router writes. Now they never share a file."""

    def scenario(self, how: str):
        r = make([("001", "a", "solo", "alongside", True, "doing worker=thr_w"), ("002", "b", "solo", "alongside", False, None)])
        approval = r / "002-b" / "APPROVED"
        human = lambda: approval.write_text("the human approved this\n")  # noqa: E731
        real_load, real_fsync, real_replace = bm.load, os.fsync, os.replace

        def after_read(root):
            board = real_load(root)
            human()
            return board

        def during_fsync(fd):
            if not approval.exists():
                human()
            return real_fsync(fd)

        def at_rename(src, dst):
            if not approval.exists():
                human()
            return real_replace(src, dst)

        patches = {"before": [], "after_read": [mock.patch.object(bm, "load", after_read)],
                   "fsync_window": [mock.patch("os.fsync", during_fsync)],
                   "before_rename": [mock.patch("os.replace", at_rename)]}[how]
        if how == "before":
            human()
        for p in patches:
            p.start()
        try:
            rc = bm.main(["--tickets", str(r), "set", "001", "review"])
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(rc, 0)
        self.assertEqual(approval.read_text(), "the human approved this\n", f"{how}: the human's approval was lost")
        self.assertEqual(status_of(r, "001-a"), "review worker=thr_w\n")
        self.assertIn("002 b solo", run(r, "next")[1], f"{how}: the approval did not reach next")

    def test_approval_survives_a_router_write_at_every_moment(self):
        for how in ("before", "after_read", "fsync_window", "before_rename"):
            with self.subTest(how=how):
                self.scenario(how)

    def test_a_human_editing_board_md_during_a_write_costs_nothing(self):
        r = make()
        view = r / "board.md"
        view.write_text("old view\n")
        real_fsync = os.fsync
        with mock.patch("os.fsync", lambda fd: (view.write_text("| 004 | docs | ready | solo | alongside | |\n"), real_fsync(fd))[1]):
            rc = bm.main(["--tickets", str(r), "set", "005", "doing", "--worker", "thr_z"])
        self.assertEqual(rc, 0)
        self.assertEqual(status_of(r, "005-other"), "doing worker=thr_z\n")
        self.assertNotIn("004", run(r, "next")[1], "a board.md edit became state")

    def test_a_set_changes_nothing_but_its_own_status_and_the_view(self):
        r = make()
        before = snapshot(r)
        run(r, "set", "005", "doing", "--worker", "thr_z")
        self.assertEqual(changed(before, snapshot(r)), {"005-other/status", "board.md"})

    def test_a_set_does_not_overwrite_another_tickets_status_changed_after_it_read(self):
        # Another router instance (or a worker hand-over) changes 001 between this set's read and its write.
        r = make()
        real_load = bm.load

        def load_then_other_writer(root):
            board = real_load(root)
            (r / "001-schema" / "status").write_text("done worker=thr_replaced\n")
            return board

        with mock.patch.object(bm, "load", load_then_other_writer):
            self.assertEqual(bm.main(["--tickets", str(r), "set", "005", "doing", "--worker", "thr_z"]), 0)
        self.assertEqual(status_of(r, "001-schema"), "done worker=thr_replaced\n", "a set rewrote a ticket it was not asked to touch")
        self.assertEqual(status_of(r, "005-other"), "doing worker=thr_z\n")

    def test_parallel_sets_all_land(self):
        r = make([(f"00{i}", f"t{i}", "solo", "alongside", True, None) for i in range(1, 7)])
        procs = [subprocess.Popen([sys.executable, str(BOARD), "--tickets", str(r), "set", f"00{i}", "doing", "--worker", f"thr_{i}"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(1, 7)]
        results = [(p.wait(timeout=60), p.stderr.read()) for p in procs]
        self.assertEqual([x[0] for x in results], [0] * 6, results)
        for i in range(1, 7):
            self.assertEqual(status_of(r, f"00{i}-t{i}"), f"doing worker=thr_{i}\n")
        run(r, "render")
        self.assertEqual((r / "board.md").read_text().count("| doing |"), 6)


class InterruptedWrite(unittest.TestCase):
    def test_a_crash_at_the_rename_leaves_the_original_whole(self):
        r = make([("001", "a", "solo", "alongside", True, "doing worker=thr_w")])
        before = snapshot(r)
        with mock.patch("os.replace", side_effect=OSError("disk gone")):
            rc = bm.main(["--tickets", str(r), "set", "001", "review"])
        self.assertEqual(rc, 2)
        self.assertEqual(snapshot(r), before)
        self.assertEqual([p.name for p in r.rglob(".tmp-*")], [])

    def test_the_new_content_arrives_by_rename_not_in_place(self):
        r = make([("001", "a", "solo", "alongside", True, "doing worker=thr_w")])
        path = r / "001-a" / "status"
        old_inode = path.stat().st_ino
        reader = open(path, "rb")                 # a reader that opened the status file before the write
        try:
            original = reader.read()
            reader.seek(0)
            self.assertEqual(run(r, "set", "001", "review")[0], 0)
            self.assertEqual(reader.read(), original, "the write truncated or rewrote the file in place")
        finally:
            reader.close()
        self.assertNotEqual(path.stat().st_ino, old_inode)


if __name__ == "__main__":
    unittest.main(verbosity=1)
