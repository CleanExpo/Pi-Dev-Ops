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
_MONEY = (r"\b(?:credit\w*|refund\w*|(?:ad-?\s?)?spend\w*|pay(?:s|ing|outs?|ments?)?"
          r"|reimburs\w*|invoic\w*"
          # Codex on b021085d: value handed out without being called money.
          r"|gift[-\s]?cards?|vouchers?|coupons?|rebates?|discounts?|fees?|waiv\w*)\b")
# "No refund auto-approval" matches too: skill text states the rule positively
# ("waits for Phill"), so a negation never has to be told apart from a grant.
_UNGATED = (r"\b(?:automatic(?:ally)?|autonomously"
            r"|auto[-\s]?(?:approv|issu|pay|refund|grant|appl|process|spend|reimburs)\w*"
            r"|without\b[^.\n]{0,30}\b(?:approv\w*|ask\w*|sign-?off|permission|consent|review"
            r"|check\w*|confirm\w*|founder|phill)"
            r"|no\s+(?:\w+\s+)?(?:approv\w*|sign-?off|permission|consent|review)"
            r"|at\s+(?:the|its|their|your)\s+(?:agent'?s?\s+|bot'?s?\s+|own\s+)?discretion)\b")
# An agent given standing authority: "CFO may approve invoices below $1,000".
_AUTH = (r"\b(?:may|can|could|will|(?:is|are)\s+(?:allowed|permitted|authori[sz]ed|free)\s+to)"
         r"\s+(?:\w+\s+){0,2}?")
_GRANT = (r"(?:(?:approv|grant|issu|releas|authori[sz]|rais|increas|appl|process|offer|giv)\w*"
          rf"[^.\n]{{0,60}}{_MONEY}|(?:refund|reimburs|pay|spend)\w*\b)")
# An agent acting on money in the present tense: "CS issues refunds on ...".
_AGENT = r"\b(?:cfo|cmo|cto|cs|tier[- ]?1|agents?|bots?|assistant|swarm|runtime)\b"
_ACTS = (r"(?:(?:approv|grant|issu|releas|authori[sz]|rais|increas|appli|process|offer|giv|waiv)e?s"
         rf"\b[^.\n]{{0,60}}{_MONEY}|(?:refund|reimburs|pay|spend)e?s\b)")
AUTONOMOUS_MONEY = re.compile(
    r"auto-?approv\w*\s+(?:refunds?|spend|ad-?spend|invoices?|up to)"
    r"|(?:refunds?|spend|ad-?spend)\s+(?:over|above|under|below|up to)\s+\$\s?\d"
    r"|request\s+(?:over|above)\s+\$\s?\d"
    # Codex round on 7da9f064: a runtime said to return or emit an approval.
    r"|returns?\s+`?approved\b"
    r"|emits?\s+`?\w*(?:spend|refund|invoice)_approved\b"
    r"|budget\s*(?:>|over|above)\s*\$\s?\d"
    # Founder ruling 21/10/2026: every service credit waits for Phill, SLA ones too.
    r"|service\s+credits?\s+(?:beyond|above|over|outside|exceeding)\b"
    # Codex rounds on 590a54b6, 9b8fc6d2 and da78588f: money handed out with no
    # approval, in either word order, in one sentence. Negations match too; skill
    # text states the rule positively ("waits for Phill").
    r"|\b(?:autonomous|automatic)\s+(?:refund|spend|pay|credit|reimburs|invoic)\w*"
    rf"|{_MONEY}[^.\n]{{0,80}}{_UNGATED}"
    rf"|{_UNGATED}[^.\n]{{0,80}}{_MONEY}"
    # Codex helper findings on 93ee19ff: standing authority to act on money.
    rf"|{_AUTH}{_GRANT}"
    # Codex on 10900da2: direct present-tense authority, "CFO approves invoices".
    rf"|{_AGENT}\s+(?:\w+\s+){{0,2}}?{_ACTS}",
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
    # Codex round on 9b8fc6d2: refunds and spend, not only credits.
    "Automatically issue refunds for billing errors.",
    "Refund duplicate charges automatically.",
    "Process refunds at the agent's discretion.",
    "Approve ad spend without asking Phill.",
    "Without sign-off, the bot pays out reimbursements under $50.",
    "Autonomously spend up to the daily budget on ads.",
    # Codex round on da78588f: auto + verb with a space, payments, permission wording.
    "Auto approve payments under $100.",
    "Auto-approve all reimbursements.",
    "The bot can issue a refund without seeking Phill's permission.",
    "Issue a refund without seeking permission.",
    "Pay invoices with no approval needed.",
    "Refunds need no sign-off from Phill.",
    "Reimburse expenses without any founder review.",
    "Auto-pay recurring vendor invoices.",
    # Negations match too, by design: the skills state the rule positively.
    "**No refund auto-approval.** Every amount waits for the founder",
    "Any refund, at any amount (founder ruling 21/10/2026: nothing auto-approves)",
    "Process autonomous refunds for duplicate charges.",
    "Issue automatic refunds for duplicate charges.",
    # Codex helper findings on 93ee19ff: an agent's standing authority.
    "CFO may approve invoices below $1,000.",
    "The support bot may grant service credits within standard SLA terms.",
    "CS can issue refunds for orders under 30 days old.",
    "The CMO bot is allowed to raise ad spend by 10% a week.",
    "Agents are authorised to release payments to known vendors.",
    # Codex on 10900da2: direct present-tense authority.
    "CFO approves invoices below $1,000.",
    "CS issues refunds on duplicate orders.",
    "The support bot grants service credits within standard SLA terms.",
    "The CMO bot raises ad spend by 10% a week.",
    "CS refunds duplicate orders.",
    "The agent pays vendor invoices on receipt.",
    # Codex on b021085d: gift cards, vouchers and other value handed out.
    "CS grants $50 gift cards on demand.",
    "The support bot may issue goodwill vouchers for billing errors.",
    "CS offers discount coupons to churn-risk accounts.",
    "The bot waives late fees for loyal customers.",
    "Agents can apply rebates to enterprise invoices.",
])
def test_detector_catches_the_retired_wording(stale):
    assert offences(stale)


@pytest.mark.parametrize("ok", [
    "Any refund, at any amount (founder ruling 21/10/2026: every amount waits for Phill)",
    "**Every refund waits for the founder.** Every amount goes through draft_review",
    "**Every spend waits for Phill.** Each spend request, at any amount, is drafted for Phill",
    "because it carries the credit-spend risk of an autonomous run",
    "3. $5000 spend request → routes through draft_review, status `pending`",
    "3. $4,500/day ad-spend → routes through draft_review, status `pending`, no real action",
    "Nothing is approved by an agent. Only Phill's own approval releases a spend.",
    "# Never cmo_adspend_approved here: approval only comes from the founder.",
    "| Per refund request | Draft for Phill; emit `cs_refund_blocked` (pending until he approves) |",
    "- Any service credit, at any amount, including credits within standard SLA terms",
    "a credit is drafted for Phill as a refund request, and it stays pending until he approves.",
    "Phill approves every refund himself.",
    "CS drafts a refund request for Phill; it stays pending until he approves.",
])
def test_detector_allows_the_current_wording(ok):
    assert offences(ok) == []
