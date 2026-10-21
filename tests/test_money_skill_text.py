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
_GIVE = r"\b(?:issue|apply|grant|give|offer|credit)(?:s|ing|ed)?\b"
_UNGATED = (r"\b(?:automatically|autonomously|without\b[^.\n]{0,25}\b(?:approval|asking|sign-?off)"
            r"|at\s+(?:the|its|their|your)\s+(?:agent'?s?\s+|bot'?s?\s+|own\s+)?discretion)")
AUTONOMOUS_MONEY = re.compile(
    r"auto-?approv\w*\s+(?:refunds?|spend|ad-?spend|invoices?|(?:service\s+)?credits?|up to)"
    r"|(?:refunds?|spend|ad-?spend)\s+(?:over|above|under|below|up to)\s+\$\s?\d"
    r"|request\s+(?:over|above)\s+\$\s?\d"
    # Codex round on 7da9f064: a runtime said to return or emit an approval.
    r"|returns?\s+`?approved\b"
    r"|emits?\s+`?\w*(?:spend|refund|invoice)_approved\b"
    r"|budget\s*(?:>|over|above)\s*\$\s?\d"
    # Founder ruling 21/10/2026: every service credit waits for Phill, SLA ones too.
    r"|service\s+credits?\s+(?:beyond|above|over|outside|exceeding)\b"
    r"|credits?\b[^.\n]{0,40}\b(?:issued|applied|granted|given)\s+(?:automatically|autonomously|without)"
    r"|auto-?(?:issue|apply|grant)\w*\s+(?:service\s+)?credits?"
    # Codex round on 590a54b6: instruction forms, in either word order.
    rf"|{_GIVE}[^.\n]{{0,60}}\bcredits?\b[^.\n]{{0,60}}{_UNGATED}"
    rf"|{_UNGATED}[^.\n]{{0,60}}{_GIVE}[^.\n]{{0,60}}\bcredits?\b",
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
    "4. $500 spend request → today the runtime returns `approved` (the gap above). Target once the",
    "| Per ad-spend request | Dual-key gate; emit `cmo_adspend_approved` or `cmo_adspend_blocked` |",
    "| Per refund request | Dual-key gate; emit `cs_refund_approved` or `cs_refund_blocked` |",
    "the bot emits cfo_invoice_approved once the amount clears",
    "- New channel launch with budget > $10,000",
    "- Service credits beyond standard SLA terms",
    "SLA credits within standard terms are issued automatically",
    "Credits under the standard SLA are applied without Phill's approval",
    "the bot auto-issues service credits up to one month's fee",
    "cs auto-approves service credits for enterprise accounts",
    "Issue service credits within standard SLA terms automatically.",
    "Apply SLA credits automatically when uptime drops below 99.9%.",
    "Automatically issue a service credit for any outage over an hour.",
    "Grant goodwill credits at the agent's discretion.",
    "Give the customer an account credit without Phill's approval.",
    "Without asking Phill, offer a credit to any churn-risk account.",
    "At its own discretion the bot grants a service credit of up to one month.",
])
def test_detector_catches_the_retired_wording(stale):
    assert offences(stale)


@pytest.mark.parametrize("ok", [
    "Any refund, at any amount (founder ruling 21/10/2026: nothing auto-approves)",
    "**No refund auto-approval.** Every amount waits for the founder",
    "3. $5000 spend request → routes through draft_review, status `pending`",
    "3. $4,500/day ad-spend → routes through draft_review, status `pending`, no real action",
    "Nothing is approved by an agent. Only Phill's own approval releases a spend.",
    "# Never cmo_adspend_approved here: approval only comes from the founder.",
    "| Per refund request | Draft for Phill; emit `cs_refund_blocked` (pending until he approves) |",
    "- Any service credit, at any amount, including credits within standard SLA terms",
    "a credit is drafted for Phill as a refund request, and it stays pending until he approves.",
])
def test_detector_allows_the_current_wording(ok):
    assert offences(ok) == []
