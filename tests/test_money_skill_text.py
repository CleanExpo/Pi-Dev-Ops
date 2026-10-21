"""Founder ruling 21/10/2026: CFO spend, CMO ad spend and CS refunds all wait for
the founder; nothing auto-approves at any amount.

Agents read skill descriptions from the catalogue (src/tao/skills.py) and from
agentskills.json / agentskills.yaml, so a stale threshold there is authority
guidance that contradicts the code. These pin that no money skill or manifest
advertises an autonomous money threshold.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MONEY_SKILLS = ("cfo", "cmo-growth", "cs-tier1", "telegram-draft-for-review")

# A claim that an agent approves money by itself, or that only amounts above
# some figure need the founder.
AUTONOMOUS_MONEY = re.compile(
    r"auto-?approv\w*\s+(?:refunds?|spend|ad-?spend|invoices?|up to)"
    r"|(?:refunds?|spend|ad-?spend)\s+(?:over|above|under|below|up to)\s+\$\s?\d"
    r"|request\s+(?:over|above)\s+\$\s?\d",
    re.IGNORECASE)


def offences(text: str) -> list[str]:
    return [m.group(0) for m in AUTONOMOUS_MONEY.finditer(text)]


@pytest.mark.parametrize("skill", MONEY_SKILLS)
def test_money_skill_text_advertises_no_autonomous_threshold(skill):
    text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    assert offences(text) == []


@pytest.mark.parametrize("manifest", ("agentskills.json", "agentskills.yaml"))
def test_manifests_advertise_no_autonomous_money_threshold(manifest):
    text = (ROOT / manifest).read_text(encoding="utf-8")
    assert offences(text) == []


@pytest.mark.parametrize("stale", [
    "drafts replies, auto-approves refunds up to $100 and routes larger ones",
    "gates ad-spend over $5,000/day through draft_review",
    "a hard gate on any ad-spend request above $5k/day",
    "an ad-spend request above $5,000/day needing the gate",
    "approve_spend auto-approves up to $1,000",
])
def test_detector_catches_the_retired_wording(stale):
    assert offences(stale)


@pytest.mark.parametrize("ok", [
    "Any refund, at any amount (founder ruling 21/10/2026: nothing auto-approves)",
    "**No refund auto-approval.** Every amount waits for the founder",
    "3. $5000 spend request → routes through draft_review, status `pending`",
    "3. $4,500/day ad-spend → routes through draft_review, status `pending`, no real action",
])
def test_detector_allows_the_current_wording(ok):
    assert offences(ok) == []
