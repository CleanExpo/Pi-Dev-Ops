"""RA-8187 AR-01 account map validator.

Every test names the why it traces to (W1-W5, recorded in the PR body's "Five whys").
Each rule test is a positive control: it plants the defect and asserts the named rule fires,
so a validator that silently passes everything cannot pass this file.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_account_map as cam  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "account_map"

_VALID = {
    "version": 1,
    "machines": [
        {"id": "mini", "host": "Phills-Mac-mini", "notes": "always-on runner"},
        {"id": "macbook", "host": None},
    ],
    "accounts": [
        {
            "label": "claude-mini",
            "provider": "claude",
            "plan": "max",
            "email": "mini@example.com",
            "machines": ["mini"],
            "notes": "",
        },
        {
            "label": "claude-macbook",
            "provider": "claude",
            "plan": None,
            "email": "macbook@example.com",
            "machines": ["macbook"],
        },
        {
            "label": "codex-mini",
            "provider": "codex",
            "plan": "chatgpt-pro",
            "email": "mini@example.com",
            "machines": ["mini", "macbook"],
        },
    ],
}


def _map(**changes):
    data = copy.deepcopy(_VALID)
    data.update(changes)
    return data


def _rules(data, **kwargs):
    return {f.rule for f in cam.validate(data, **kwargs).errors}


def test_valid_map_has_no_errors():
    """W4.5: a well-formed map passes, so the failures below are caused by their plants."""
    report = cam.validate(_map())
    assert report.errors == []


# ── W1: emails only, no secrets ──────────────────────────────────────────────


@pytest.mark.parametrize("key", ["token", "api_key", "password", "session_cookie", "oauthToken"])
def test_secret_named_key_on_account_is_rejected(key):
    """W1.4: a secret-named field is rejected by name, wherever it sits."""
    data = _map()
    data["accounts"][0][key] = "x"
    assert "SECRET_FIELD" in _rules(data)


def test_secret_named_key_at_top_level_and_on_machine_is_rejected():
    """W1.4: the name check covers every level, not just accounts."""
    data = _map()
    data["refresh_token"] = "x"
    data["machines"][0]["Secret"] = "x"
    errors = [f for f in cam.validate(data).errors if f.rule == "SECRET_FIELD"]
    assert len(errors) == 2


def test_unknown_key_is_rejected():
    """W1.4: an allowlist, so a new field name the secret list does not know still fails."""
    data = _map()
    data["accounts"][0]["login_blob"] = "x"
    assert "UNKNOWN_KEY" in _rules(data)


@pytest.mark.parametrize(
    "value",
    [
        "sk-" + "a1B2c3D4e5F6g7H8i9J0k",
        "Bearer " + "abc.def.ghi",
        "ghp_" + "A" * 36,
        "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxIn0.sig",
        "-----BEGIN " + "PRIVATE KEY-----",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "Q3VzdG9t" + "ZXJUb2tlbjEyMzQ1Njc4OTAx",
    ],
)
def test_secret_looking_value_in_notes_is_rejected(value):
    """W1.3: a credential pasted into an allowed field (notes) is still caught."""
    data = _map()
    data["accounts"][0]["notes"] = f"pasted {value} here"
    assert "SECRET_VALUE" in _rules(data)


def test_plain_notes_with_ticket_ids_pass_and_urls_fail_closed():
    """W1.3/W6.3: plain prose with a ticket id passes; a URL is not an accepted notes shape
    (accept-only redesign), so it fails closed instead of being trusted."""
    data = _map()
    data["accounts"][0]["notes"] = "Seat decision pending (RA-8196), ask Phill first."
    assert cam.validate(data).errors == []
    data["accounts"][0]["notes"] = "see https://linear.app/unite-group/issue/RA-8196"
    assert "BAD_VALUE" in _rules(data)


# ── W2: exactly one Claude pin per machine ───────────────────────────────────


def test_machine_with_no_claude_pin_fails():
    """W2.4: zero Claude accounts on a machine leaves the router nothing to charge."""
    data = _map()
    data["machines"].append({"id": "pc"})
    assert "CLAUDE_PIN_MISSING" in _rules(data)


def test_machine_with_two_claude_pins_fails():
    """W2.3: two Claude accounts on one machine invites login switching to stack quotas."""
    data = _map()
    data["accounts"].append(
        {"label": "claude-mini-2", "provider": "claude", "plan": "max",
         "email": "other@example.com", "machines": ["mini"]}
    )
    assert "CLAUDE_PIN_MULTIPLE" in _rules(data)


def test_pin_to_undeclared_machine_fails():
    """W2.2: a pin the router cannot place is a misroute waiting to happen."""
    data = _map()
    data["accounts"][2]["machines"] = ["mini", "laptop-x"]
    assert "UNKNOWN_MACHINE" in _rules(data)


def test_duplicate_machine_id_fails():
    """W2.2: two machines with one id make every pin to it ambiguous."""
    data = _map()
    data["machines"].append({"id": "mini"})
    assert "DUPLICATE_MACHINE" in _rules(data)


def test_account_with_no_machines_fails():
    """W2.1: an account pinned nowhere cannot be routed or charged."""
    data = _map()
    data["accounts"][2]["machines"] = []
    assert "SCHEMA" in _rules(data)


# ── W3: shared Claude email across machines ──────────────────────────────────


def test_same_claude_email_on_two_entries_fails():
    """W3.1: two machines on one Claude account share one limit the router counts twice."""
    data = _map()
    data["accounts"][1]["email"] = "mini@example.com"
    assert "SHARED_CLAUDE_EMAIL" in _rules(data)


def test_one_claude_entry_pinned_to_two_machines_fails():
    """W3.2: the same sharing, written as one entry with two pins."""
    data = _map()
    data["accounts"] = [a for a in data["accounts"] if a["label"] != "claude-macbook"]
    data["accounts"][0]["machines"] = ["mini", "macbook"]
    assert "SHARED_CLAUDE_EMAIL" in _rules(data)


def test_shared_claude_email_is_case_insensitive():
    """W3.4: A@x and a@x are one mailbox; case must not defeat the check."""
    data = _map()
    data["accounts"][1]["email"] = "MINI@Example.com"
    assert "SHARED_CLAUDE_EMAIL" in _rules(data)


def test_shared_codex_email_is_not_a_claude_finding():
    """W3.5: the rule is about Claude pins; Codex sharing is out of this ticket's scope."""
    assert "SHARED_CLAUDE_EMAIL" not in _rules(_map())


# ── W4: schema shape ─────────────────────────────────────────────────────────


def test_unknown_provider_fails():
    """W4.2: only the three subscription accounts; anything else is a banned API-key lane."""
    data = _map()
    data["accounts"][2]["provider"] = "openrouter"
    assert "BAD_PROVIDER" in _rules(data)


def test_duplicate_label_fails():
    """W4.3: the ledger and Ops Board key on label; duplicates merge two accounts."""
    data = _map()
    data["accounts"][2]["label"] = "claude-mini"
    assert "DUPLICATE_LABEL" in _rules(data)


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "two@@example.com", "", 42])
def test_malformed_email_fails(email):
    """W4.4: a typo'd email is a pin to nobody that looks like a real account."""
    data = _map()
    data["accounts"][0]["email"] = email
    assert "BAD_EMAIL" in _rules(data)


@pytest.mark.parametrize("field", ["label", "provider", "plan", "email", "machines"])
def test_missing_required_field_fails(field):
    """W4.1: readers need a stable shape."""
    data = _map()
    del data["accounts"][0][field]
    assert "MISSING_FIELD" in _rules(data)


@pytest.mark.parametrize(
    "data",
    [None, [], {"version": 2, "machines": [], "accounts": []}, {"version": 1}],
)
def test_bad_top_level_shape_fails(data):
    """W4.1: an empty or wrong-version file must never read as an empty valid map."""
    assert "SCHEMA" in _rules(data)


# ── W5: placeholders are pending, never live ─────────────────────────────────


def test_invalid_domain_email_is_reported_pending_not_error():
    """W5.4: a reserved .invalid placeholder passes shape but is counted as pending."""
    data = _map()
    data["accounts"][1]["email"] = "claude-macbook@pending.invalid"
    report = cam.validate(data)
    assert report.errors == []
    assert any("claude-macbook" in p for p in report.pending)


def test_null_plan_is_reported_pending():
    """W5.1: an undecided plan is Phill's open decision, shown as pending."""
    report = cam.validate(_map())
    assert any("claude-macbook" in p and "plan" in p for p in report.pending)


def test_require_real_fails_on_placeholder_email():
    """W5.4: --require-real is the switch that refuses to route on placeholders."""
    data = _map()
    data["accounts"][1]["email"] = "claude-macbook@pending.invalid"
    assert "PENDING_EMAIL" in _rules(data, require_real=True)


def test_identical_placeholders_still_count_as_shared():
    """W5.3: placeholders must be distinct per machine; identical ones are still shared."""
    data = _map()
    data["accounts"][0]["email"] = "claude-mini@pending.invalid"
    data["accounts"][1]["email"] = "claude-mini@pending.invalid"
    assert "SHARED_CLAUDE_EMAIL" in _rules(data)
