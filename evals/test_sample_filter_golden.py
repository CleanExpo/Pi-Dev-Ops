"""Prove-It Gate (RA-7023) — golden regression eval for sample-and-filter synthesis.

Deterministic assertions over tao_sample_filter.cluster and shortlist (AlphaCode
`top_k(rerank(cluster(sample_N)))`). Pins near-duplicate collapse and top-k
selection against silent regression. No LLM judge.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.server import tao_sample_filter as sf

_GOLDEN = Path(__file__).parent / "golden" / "sample_filter.yaml"
_DATA = yaml.safe_load(_GOLDEN.read_text())


@pytest.mark.parametrize("case", _DATA["cluster"], ids=lambda c: "".join(c["survivors"]))
def test_cluster_keeps_best_representative(case: dict) -> None:
    cands = [sf.Candidate(**c) for c in case["candidates"]]
    survivors = [c.id for c in sf.cluster(cands)]
    assert survivors == case["survivors"]


@pytest.mark.parametrize("case", _DATA["shortlist"], ids=lambda c: "".join(c["result"]))
def test_shortlist_top_k(case: dict) -> None:
    cands = [sf.Candidate(**c) for c in case["candidates"]]
    result = [c.id for c in sf.shortlist(cands, case["k"])]
    assert result == case["result"]


@pytest.mark.parametrize("case", _DATA["invalid"], ids=lambda c: f"k={c['k']}")
def test_invalid_k_raises(case: dict) -> None:
    cands = [sf.Candidate(**c) for c in case["candidates"]]
    with pytest.raises(ValueError):
        sf.shortlist(cands, case["k"])
