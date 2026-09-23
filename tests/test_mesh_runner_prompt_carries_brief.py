"""The claim carries the ticket's brief, so the execution node needs no Linear access.

Measured 2026-09-23: a Mac-mini mesh run of UNI-2744 received a prompt naming only the
identifier, tried four routes to read the ticket, found none, and stopped without
changing code. These controls pin the fix and the refusal path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesh"))

from prompt import build_prompt  # noqa: E402


BRANCH = "mesh/phills-mac-mini/uni-2744-abc123"


def test_prompt_carries_title_and_description():
    prompt = build_prompt(
        {"title": "Dedupe the admission-drop warning",
         "description": "Log the first occurrence and a periodic count."},
        "UNI-2744", BRANCH,
    )
    assert "UNI-2744" in prompt
    assert "Dedupe the admission-drop warning" in prompt
    assert "Log the first occurrence and a periodic count." in prompt
    assert BRANCH in prompt


def test_missing_brief_refuses_instead_of_guessing():
    """The control that matters. An absent brief must produce a STOP instruction,
    never a bare 'work ticket X' that invites a guess."""
    prompt = build_prompt({}, "UNI-2744", BRANCH)
    lowered = prompt.lower()
    assert "do not guess" in lowered
    assert "do not change any code" in lowered
    assert "stop" in lowered
    # It must NOT read as a normal work instruction.
    assert "make a small, verifiable change" not in lowered


@pytest.mark.parametrize("claim", [
    {"title": "", "description": ""},
    {"title": None, "description": None},
    {"title": "   ", "description": "\n\t "},
])
def test_present_but_empty_is_treated_as_absent(claim):
    """`""` and whitespace are present-but-absent; they must take the refusal path."""
    assert "do not guess" in build_prompt(claim, "UNI-2744", BRANCH).lower()


def test_title_only_is_enough_to_work():
    prompt = build_prompt({"title": "Fix the flaky import"}, "UNI-1", BRANCH)
    assert "Fix the flaky import" in prompt
    assert "do not guess" not in prompt.lower()
