"""Tests for swarm._atomic — crash-safe file write helper.

The contract under test: if a crash occurs between writing the temp file
and renaming it into place, the ORIGINAL file is preserved intact. A
naive `path.write_text(...)` truncates the file to zero bytes before
re-writing it; this helper does not.

Per [[board-deliberation-code-patterns-2026-05-15]] PR2 failure-mode
documentation: "old state preserved on crash".
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm._atomic import atomic_write_json, atomic_write_text


class AtomicWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._dir.name)

    def tearDown(self) -> None:
        self._dir.cleanup()

    # ── happy path ────────────────────────────────────────────────────────

    def test_atomic_write_text_creates_file(self) -> None:
        p = self.tmpdir / "state.json"
        atomic_write_text(p, '{"hello": "world"}')
        self.assertEqual(p.read_text(), '{"hello": "world"}')

    def test_atomic_write_json_round_trip(self) -> None:
        p = self.tmpdir / "state.json"
        atomic_write_json(p, {"offset": 42})
        self.assertEqual(json.loads(p.read_text()), {"offset": 42})

    def test_atomic_write_json_with_trailing_newline(self) -> None:
        p = self.tmpdir / "state.json"
        atomic_write_json(p, {"offset": 1}, newline=True)
        self.assertTrue(p.read_text().endswith("\n"))

    def test_no_tmp_file_left_behind_on_success(self) -> None:
        p = self.tmpdir / "state.json"
        atomic_write_text(p, "ok")
        self.assertFalse(p.with_name(p.name + ".tmp").exists())

    def test_parent_dir_created_if_missing(self) -> None:
        p = self.tmpdir / "subdir" / "state.json"
        atomic_write_json(p, {"x": 1})
        self.assertTrue(p.exists())

    # ── crash safety (the load-bearing claim) ─────────────────────────────

    def test_old_file_preserved_when_serialization_crashes(self) -> None:
        """If json.dumps raises mid-write, the OLD file must survive."""
        p = self.tmpdir / "state.json"
        atomic_write_json(p, {"good": "original"})
        original = p.read_text()

        # Object that fails serialisation
        class Unserialisable:
            pass

        with self.assertRaises(TypeError):
            atomic_write_json(p, {"bad": Unserialisable()})

        # OLD content intact
        self.assertEqual(p.read_text(), original)
        self.assertFalse(p.with_name(p.name + ".tmp").exists())

    def test_old_file_preserved_when_tmp_write_crashes(self) -> None:
        """Simulate disk-full / SIGKILL between tmp write and os.replace."""
        p = self.tmpdir / "state.json"
        atomic_write_json(p, {"good": "original"})
        original = p.read_text()

        with patch("swarm._atomic.os.replace") as mock_replace:
            mock_replace.side_effect = OSError("simulated crash before rename")
            with self.assertRaises(OSError):
                atomic_write_json(p, {"bad": "new"})

        # OLD content intact — the rename never completed
        self.assertEqual(p.read_text(), original)

    def test_first_write_creates_file_without_clobbering(self) -> None:
        """Atomic write to a path with no prior file is still safe."""
        p = self.tmpdir / "fresh.json"
        self.assertFalse(p.exists())
        atomic_write_json(p, {"hello": "world"})
        self.assertEqual(json.loads(p.read_text()), {"hello": "world"})


if __name__ == "__main__":
    unittest.main()
