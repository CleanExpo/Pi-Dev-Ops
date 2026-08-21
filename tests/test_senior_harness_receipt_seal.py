"""The startup receipt must not be forgeable by whoever can write the state file.

Every digest in the receipt is computed FROM the receipt by a public function, so
a holder of the state file can rewrite any field and recompute every digest. Review
round 1 at 8cc7100d..853bc244 filed this as a P1 and it was confirmed by execution:
a /grill-me session (strict, mutation denied) was converted to a delivery session
and Write was admitted, once every objective-derived field was re-derived and
re-signed consistently.

The reproduction below is that confirmed attack, expressed as a test. It needs the
driver's own decide_route() to rebuild route_decision, because the two shallower
versions of the tamper are already refused (stale task_id, then stale route
decision) — stopping at either of those produces a false refutation.

Scope, so the severity is not overstated: the attacker must already be able to
write under SENIOR_HARNESS_STATE_DIR. This is defence in depth, not remote code
execution. But the whole point of the control is to hold when something local has
gone wrong, so a public-digest-only receipt does not do its job.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import setup_driver as setup_driver_module  # noqa: E402
from senior_harness import digest  # noqa: E402


def _reseal_public_digests(receipt: dict) -> None:
    """Recompute every public digest the way an attacker with the file would."""
    contract = receipt["setup_contract"]
    unsigned_contract = dict(contract)
    unsigned_contract.pop("setup_contract_digest", None)
    contract["setup_contract_digest"] = digest(unsigned_contract)
    unsigned_receipt = dict(receipt)
    unsigned_receipt.pop("receipt_integrity_digest", None)
    unsigned_receipt.pop("receipt_seal", None)
    receipt["receipt_integrity_digest"] = digest(unsigned_receipt)


def test_reforged_state_cannot_downgrade_a_grill_session_to_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "seal-downgrade", "cwd": str(REPO_ROOT)}

    setup_driver_module.handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "/grill-me shape recovery"},
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = setup_driver_module._state_path(REPO_ROOT.resolve(), "seal-downgrade")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    contract = state["receipt"]["setup_contract"]
    assert contract["interaction"] == "grill-me", "precondition: session starts locked down"

    # The confirmed attack: rewrite the objective and interaction, then re-derive
    # EVERY field the objective drives so no consistency check catches it.
    forged = "Develop the Senior Harness"
    contract["literal_objective"] = forged
    contract["interaction"] = "delivery"
    contract["objective_digest"] = digest({"task": forged})
    contract["task_id"] = digest({"task": forged})[7:23]
    contract["routing_request"]["task"] = forged
    contract["route_decision"] = setup_driver_module.decide_route(
        contract["routing_request"]
    ).to_dict()
    state["first_tool_admitted"] = True
    _reseal_public_digests(state["receipt"])
    state_path.write_text(json.dumps(state), encoding="utf-8")

    result = setup_driver_module.handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {}},
        surface="claude",
        event="PreToolUse",
    )
    output = result["hookSpecificOutput"]

    assert output.get("permissionDecision") == "deny", (
        "a re-forged state file downgraded a grill session to delivery and admitted "
        f"Write: {output}"
    )


def test_a_receipt_from_an_older_driver_heals_on_the_next_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt issued before the seal existed must recover, not strand the session.

    Observed for real on 2026-08-22: adding the seal check without this path denied
    every mediated tool in every already-running session on the machine, with no way
    back — a prompt could not help, because the prompt handler validated the same
    unverifiable receipt and propagated. That is the same failure class as the
    drift-deny bug this branch exists to fix, one layer down.

    The contract: an unverifiable prior receipt falls through to a fresh admission,
    and the fresh receipt is sealed. Denial is reserved for a receipt that is
    present and WRONG, which is the forgery case.
    """
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "legacy-heal", "cwd": str(REPO_ROOT)}

    setup_driver_module.handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Legacy session"},
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = setup_driver_module._state_path(REPO_ROOT.resolve(), "legacy-heal")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Corrupt the integrity digest rather than stripping the seal. Both raise the
    # same SetupError out of validate_startup_receipt, so this exercises the same
    # fall-through — but it stays meaningful whether or not the seal check is
    # currently wired, which is what makes it safe to trust when re-arming that
    # check. "Any unverifiable prior receipt heals" is the real contract; a missing
    # seal is only one instance of it.
    state["receipt"]["receipt_integrity_digest"] = "sha256:" + "0" * 64
    state_path.write_text(json.dumps(state), encoding="utf-8")

    healed = setup_driver_module.handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "the next prompt"},
        surface="claude",
        event="UserPromptSubmit",
    )
    assert "froze the primary objective" in healed["hookSpecificOutput"]["additionalContext"], (
        "an unsealed legacy receipt did not trigger re-admission: "
        f"{healed['hookSpecificOutput']}"
    )
    reissued = json.loads(state_path.read_text(encoding="utf-8"))
    assert "receipt_seal" in reissued["receipt"], "the reissued receipt must be sealed"

    # Read, not Write. "Healed" means the session is no longer STRANDED — its
    # receipt verifies and the objective lock is live again. Whether a root
    # session may itself mutate is a separate policy (parallel fanout requires
    # mutations to be owned by leaf workers), and asserting Write here would
    # couple this regression test to that unrelated rule and fail for the wrong
    # reason.
    after = setup_driver_module.handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="claude",
        event="PreToolUse",
    )
    assert "permissionDecision" not in after["hookSpecificOutput"], (
        f"session still stranded after healing: {after['hookSpecificOutput']}"
    )


def test_an_untampered_session_is_still_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the seal must not break ordinary sessions.

    Without this, the test above passes trivially if the receipt is rejected
    always — which would deny every tool in every session.
    """
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "seal-clean", "cwd": str(REPO_ROOT)}

    setup_driver_module.handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Develop the Senior Harness"},
        surface="claude",
        event="UserPromptSubmit",
    )
    result = setup_driver_module.handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="claude",
        event="PreToolUse",
    )
    assert "permissionDecision" not in result["hookSpecificOutput"]
