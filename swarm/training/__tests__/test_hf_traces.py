"""Tests for swarm.training.hf_traces — the labelled-corpus capture layer."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _reload(traces_root: Path):
    os.environ["TAO_HF_TRACES_ROOT"] = str(traces_root)
    import importlib
    from swarm.training import hf_traces as mod
    importlib.reload(mod)
    return mod


class RecordTests(unittest.TestCase):
    def test_record_writes_jsonl_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            p = mod.record(
                worker="preamble_trainer",
                task="summarise_corpus",
                input_text="hello",
                output_text="world",
                input_context={"context_id": "x"},
                output_structured={"people": []},
                msg_count=12,
            )
            self.assertTrue(p.exists())
            row = json.loads(p.read_text().strip())
        self.assertEqual(row["worker"], "preamble_trainer")
        self.assertEqual(row["task"], "summarise_corpus")
        self.assertEqual(row["input"]["text"], "hello")
        self.assertEqual(row["output"]["text"], "world")
        self.assertEqual(row["input"]["context"]["context_id"], "x")
        self.assertEqual(row["output"]["structured"]["people"], [])
        self.assertEqual(row["metadata"]["msg_count"], 12)
        # File path follows the worker/date pattern
        self.assertTrue("preamble_trainer" in str(p))

    def test_truncates_very_long_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            big = "X" * (20 * 1024)
            mod.record(worker="x", task="t", input_text=big, output_text=big)
            p = next((Path(tmp) / "x").glob("*.jsonl"))
            row = json.loads(p.read_text().strip())
        # Each field truncated to 16 KB
        self.assertEqual(len(row["input"]["text"]), 16 * 1024)
        self.assertEqual(len(row["output"]["text"]), 16 * 1024)

    def test_appends_multiple_rows_to_same_daily_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            for i in range(3):
                mod.record(worker="w", task="t", input_text=f"in{i}", output_text=f"out{i}")
            p = next((Path(tmp) / "w").glob("*.jsonl"))
            rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["input"]["text"] for r in rows], ["in0", "in1", "in2"])


class SummariseTests(unittest.TestCase):
    def test_counts_by_worker_and_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            mod.record(worker="preamble_trainer", task="summarise", input_text="a", output_text="b")
            mod.record(worker="preamble_trainer", task="summarise", input_text="c", output_text="d")
            mod.record(worker="pm_scoper", task="scope", input_text="e", output_text="f")
            r = mod.summarise()
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["by_worker"], {"preamble_trainer": 2, "pm_scoper": 1})
        self.assertEqual(r["by_task"], {"summarise": 2, "scope": 1})
        self.assertEqual(r["target_for_finetune"], 5000)
        # Progress is 3/5000 = 0.06% rounded to 1 dp
        self.assertEqual(r["progress_pct"], 0.1)

    def test_empty_root_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            r = mod.summarise()
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["by_worker"], {})
        self.assertEqual(r["progress_pct"], 0.0)


class UploadGuardTests(unittest.TestCase):
    def test_no_token_returns_none_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            # Ensure HF_TOKEN is NOT set
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HF_TOKEN", None)
                result = mod.upload_to_hub_if_token(dataset_name="anyone/anything")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
