"""Nexus One first vertical pilot — SYNTHETIC, non-production slice.

Journey: Margot accept/resume → one canonical task → Max-subscription
worker path (named, never billed) → deterministic checks → independent
Judge hook → durable receipt.

This package is not registered on the FastAPI app, does not enroll a
worker, and must not be treated as shipped Mission Control behaviour.
"""
from .entry import accept_or_resume, run_method
from .journey import run_pilot
from .policy import select_worker
from .review import invoke_independent_review
from .store import SyntheticStore
from .types import LINEAGE, SYNTHETIC_FIXTURE_ID, SYNTHETIC_MARKER

__all__ = [
    "LINEAGE",
    "SYNTHETIC_FIXTURE_ID",
    "SYNTHETIC_MARKER",
    "SyntheticStore",
    "accept_or_resume",
    "invoke_independent_review",
    "run_method",
    "run_pilot",
    "select_worker",
]
