"""Duplicate-key-safe JSON parsing for jev_platform (re-exported as client.strict_json)."""
from __future__ import annotations

import json


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise json.JSONDecodeError(f"duplicate key {k!r}", "", 0)  # malformed, to every caller
        out[k] = v
    return out


def strict_json(raw):
    """Round 26-27: json.loads keeps the LAST of two equal keys, so q=0.01 then q=0.99 read as a pass. Any
    duplicate key raises json.JSONDecodeError instead. Every JSON parse in jev_platform/ and
    evals/jev_constitution/ goes through here (except private json.dumps round-trip snapshots)."""
    return json.loads(raw, object_pairs_hook=_no_duplicates)
