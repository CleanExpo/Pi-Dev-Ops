from __future__ import annotations

from scripts.fallback_dryrun import _remediation_steps

# A billing rejection is a valid, authenticated key hitting an unfunded account
# (HTTP 400, not 401). The remediation must point the operator at funding, not at
# the generic key/package checks that would misdirect them. See RA-6886 / R-02.

_BILLING_MESSAGES = [
    "BadRequestError: Error code: 400 - Your credit balance is too low to access the Anthropic API.",
    "Your account balance is too low. Go to Plans & Billing to add credits.",
]

_GENERIC_MESSAGES = [
    "AuthenticationError — ANTHROPIC_API_KEY is invalid or expired",
    "anthropic package not installed — run: pip install anthropic",
    "APIConnectionError — cannot reach api.anthropic.com",
    "Sentinel 'FALLBACK_OK' not found in response",
]


def test_billing_messages_get_funding_guidance():
    for msg in _BILLING_MESSAGES:
        steps = _remediation_steps(msg)
        assert "billing failure" in steps.lower()
        assert "Plans & Billing" in steps


def test_generic_messages_get_key_and_package_guidance():
    for msg in _GENERIC_MESSAGES:
        steps = _remediation_steps(msg)
        assert "billing failure" not in steps.lower()
        assert "ANTHROPIC_API_KEY" in steps
        assert "anthropic" in steps.lower()


def test_classifier_is_case_insensitive():
    assert "billing failure" in _remediation_steps(
        "CREDIT BALANCE IS TOO LOW"
    ).lower()
