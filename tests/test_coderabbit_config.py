"""CodeRabbit must not review pull requests automatically (see .coderabbit.yaml).

Founder, 16/11/2026: Codex is the reviewer, stop using CodeRabbit. main requires
every review conversation to be resolved, so an automatic CodeRabbit thread that
lands after a PR is marked ready blocks a merge whose checks are all green. This
fails if the file is removed or automatic reviews are turned back on.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / ".coderabbit.yaml"


def test_coderabbit_automatic_reviews_are_off() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    auto_review = config["reviews"]["auto_review"]
    # CodeRabbit's default is enabled, so a missing key counts as on.
    assert auto_review.get("enabled", True) is False
