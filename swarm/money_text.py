"""swarm/money_text.py — does a draft talk about money?

Founder ruling 21/10/2026: every refund, credit, payment and spend waits for
Phill. draft_review's reversible tier auto-sends without review, so a draft
that mentions money is sent to review instead, whatever reversibility its
caller claimed. Deliberately broad (any digit counts): a false positive costs
one review card, a false negative sends money talk unreviewed.
"""
from __future__ import annotations

import re

_MONEY = re.compile(
    r"\b(?:refund\w*|credit\w*|reimburs\w*|payments?|pay(?:s|ing|outs?|able)?|paid"
    r"|invoic\w*|spend\w*|charge[sd]?|billing|budget\w*|discount\w*|price\w*|cost\w*"
    r"|fees?|waiv\w*|vouchers?|rebates?|compensat\w*|complimentary|coupons?|promo\w*"
    r"|gift[- ]?cards?|balances?|writ\w*[- ]off|money|cash|funds?|bucks|cents?"
    r"|transfer\w*|certificates?|points?|loyalty|rewards?|free|dollars?|deposit\w*|wire\w*)\b"
    # Any digit at all: an amount, with or without a currency, before or after it.
    r"|[$€£¥]|\d",
    re.IGNORECASE)


def mentions_money(text: str) -> bool:
    """True when the text names money or an amount (see _MONEY)."""
    return bool(_MONEY.search(text or ""))


__all__ = ["mentions_money"]
