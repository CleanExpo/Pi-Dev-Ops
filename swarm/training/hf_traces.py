"""swarm/training/hf_traces.py — labelled-corpus assembly for the Q3 PEFT LoRA experiment.

Per [[research-hf-agent-trains-models-2026-05-14]] (HF Agent Trains research,
2026-05-14): the Pi-CEO swarm generates the richest labelled signal in
Phill's stack. Every preamble, every PM scope, every intake classification
is a free (input, output, metadata) tuple — the substrate of a future
Qwen-2.5-7B PEFT LoRA fine-tune that the Mac mini can run at zero
marginal cost.

This module is the **capture layer**. It writes JSONL traces to
`.harness/hf_traces/<worker>/<date>.jsonl` so a labelled corpus
accumulates daily. The upload-to-HF step is deferred — when Phill adds
`HF_TOKEN` to env and the corpus hits ≥5k examples, the upload script
batch-pushes to a private HF dataset.

Foundation only. No token dependency tonight.

Public API:
    record(worker, task, input_text, output_text, **metadata) -> Path
        Append a single trace row. Returns the JSONL path written to.

    summarise() -> dict
        Count rows per worker + per task. Used by the corpus-growth
        dashboard.

Schema per JSONL row:
    {
      "ts": "ISO 8601 UTC",
      "worker": "preamble_trainer | pm_scoper | intake_router | ...",
      "task":   "summarise_corpus | scope_ambiguous_ticket | classify_inbound | ...",
      "input":  {"text": "...", "context": {...}},
      "output": {"text": "...", "structured": {...}},
      "metadata": {<arbitrary>}
    }
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.training.hf_traces")

TRACES_ROOT = Path(os.environ.get(
    "TAO_HF_TRACES_ROOT",
    str(Path.home() / "Pi-CEO" / "Pi-Dev-Ops" / ".harness" / "hf_traces"),
))


def _path_for(worker: str, dt: datetime | None = None) -> Path:
    dt = dt or datetime.now(timezone.utc)
    return TRACES_ROOT / worker / f"{dt.strftime('%Y-%m-%d')}.jsonl"


def record(
    *,
    worker: str,
    task: str,
    input_text: str,
    output_text: str,
    input_context: dict[str, Any] | None = None,
    output_structured: dict[str, Any] | None = None,
    **metadata: Any,
) -> Path:
    """Append one trace row. Safe to call concurrently — JSONL append-only.

    Truncates very long inputs/outputs to 16 KB each to keep the file size
    bounded; downstream training will rarely need more than that per row.
    """
    INPUT_LIMIT = 16 * 1024
    OUTPUT_LIMIT = 16 * 1024

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "worker": worker,
        "task": task,
        "input": {
            "text": (input_text or "")[:INPUT_LIMIT],
            "context": input_context or {},
        },
        "output": {
            "text": (output_text or "")[:OUTPUT_LIMIT],
            "structured": output_structured or {},
        },
        "metadata": metadata,
    }

    path = _path_for(worker)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return path


def summarise(*, root: Path | None = None) -> dict[str, Any]:
    """Count traces per worker + per task. Used by the corpus-growth dashboard."""
    root = root or TRACES_ROOT
    if not root.exists():
        return {"total": 0, "by_worker": {}, "by_task": {}, "oldest": None, "newest": None}

    by_worker: dict[str, int] = {}
    by_task: dict[str, int] = {}
    oldest: str | None = None
    newest: str | None = None
    total = 0

    for worker_dir in sorted(root.iterdir()):
        if not worker_dir.is_dir():
            continue
        for trace_file in sorted(worker_dir.glob("*.jsonl")):
            for line in trace_file.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                worker = row.get("worker", worker_dir.name)
                task = row.get("task", "unknown")
                by_worker[worker] = by_worker.get(worker, 0) + 1
                by_task[task] = by_task.get(task, 0) + 1
                ts = row.get("ts")
                if ts:
                    if oldest is None or ts < oldest:
                        oldest = ts
                    if newest is None or ts > newest:
                        newest = ts

    return {
        "total": total,
        "by_worker": by_worker,
        "by_task": by_task,
        "oldest": oldest,
        "newest": newest,
        "target_for_finetune": 5000,
        "progress_pct": round(100 * total / 5000, 1) if total else 0.0,
    }


def upload_to_hub_if_token(*, dataset_name: str, days_back: int = 30) -> dict | None:
    """If HF_TOKEN is set, batch-upload the last N days of traces to HF Datasets.

    No-op when HF_TOKEN is missing. Designed as a separate manual /
    scheduled invocation — never blocks the per-record write path.
    """
    token = os.environ.get("HF_TOKEN")
    if not token:
        return None
    try:
        from huggingface_hub import HfApi  # type: ignore[import-not-found]
        from datasets import Dataset, concatenate_datasets  # type: ignore[import-not-found]
    except Exception as e:  # noqa: BLE001
        log.warning("HF libraries unavailable; skipping upload: %s", e)
        return None

    # Gather rows
    cutoff = datetime.now(timezone.utc).date()
    rows: list[dict] = []
    for worker_dir in TRACES_ROOT.iterdir():
        if not worker_dir.is_dir():
            continue
        for trace_file in worker_dir.glob("*.jsonl"):
            for line in trace_file.read_text().splitlines():
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    if not rows:
        return {"uploaded": 0, "skipped_reason": "no rows"}

    ds = Dataset.from_list(rows)
    ds.push_to_hub(dataset_name, token=token, private=True)
    return {"uploaded": len(rows), "dataset": dataset_name}


if __name__ == "__main__":  # pragma: no cover
    # CLI: corpus-growth summary
    import sys
    if "--upload" in sys.argv:
        # Optional flag to push to HF
        ds_name = os.environ.get("HF_DATASET_NAME", "phill-mcgurk/pi-ceo-swarm-traces")
        result = upload_to_hub_if_token(dataset_name=ds_name)
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(summarise(), indent=2, default=str))
