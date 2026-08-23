"""Focused tests for receipt and binding validation."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _pretool,
    _rehash_receipt,
    _start_hook_session,
    admit_startup,
    build_setup_contract,
    digest,
    json,
    pytest,
    setup_driver_module,
    validate_startup_receipt,
)

MALFORMED_DIGEST_CASES = [
    ("missing", None),
    ("object", {"digest": "sha256:" + "0" * 64}),
    ("upper-case", "sha256:" + "A" * 64),
    ("short", "sha256:abc"),
    ("wrong-prefix", "sha512:" + "0" * 64),
]
MALFORMED_SKILL_CASES = [
    ("skills-list", "no required-skill evidence"),
    ("skill-list", "missing skill senior-harness"),
    ("missing-path", "path is missing or invalid"),
    ("object-path", "path is missing or invalid"),
    ("relative-path", "path is missing or invalid"),
    ("unavailable-path", "skill is unavailable or invalid"),
    ("wrong-name", "skill name is missing or invalid"),
]


def _malform_skill_binding(skills: dict, case: str, tmp_path: Path) -> None:
    if case == "skill-list":
        skills["senior-harness"] = []
    elif case == "missing-path":
        skills["senior-harness"].pop("path")
    elif case == "object-path":
        skills["senior-harness"]["path"] = {"path": str(REPO_ROOT)}
    elif case == "relative-path":
        skills["senior-harness"]["path"] = "skills/senior-harness"
    elif case == "unavailable-path":
        skills["senior-harness"]["path"] = str(tmp_path / "missing-skill")
    else:
        skills["senior-harness"]["name"] = "delivery"


@pytest.mark.parametrize(
    ("objective", "interaction"),
    [
        ("/grill-me shape recovery", "grill-me"),
        ("  $grill-me shape recovery", "grill-me"),
        ("/grill-with-docs shape recovery", "grill-with-docs"),
        ("\t$grill-with-docs shape recovery", "grill-with-docs"),
        ("/grill-me: shape recovery", "grill-me"),
        ("Discuss /grill-me without invoking it", "delivery"),
    ],
)
def test_interaction_is_derived_from_the_exact_objective_prefix(
    objective: str, interaction: str
) -> None:
    receipt = admit_startup(
        build_setup_contract(
            objective, REPO_ROOT, surface="codex", interaction=interaction
        )
    )
    assert validate_startup_receipt(receipt)["status"] == "valid"


def test_trusted_reissued_receipt_still_cannot_mismatch_grill_interaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state",
        monkeypatch,
        session_id="rewritten-grill-interaction",
        prompt="$grill-with-docs shape recovery",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipt"]["setup_contract"]["interaction"] = "delivery"
    _rehash_receipt(state["receipt"])
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "interaction does not match the frozen literal objective"
        in denied["hookSpecificOutput"]["permissionDecisionReason"]
    )


@pytest.mark.parametrize("shape", [[], "scalar"], ids=["list", "scalar"])
@pytest.mark.parametrize("layer", ["state", "receipt", "setup-contract"])
def test_non_object_startup_layers_enter_the_deterministic_invalid_state_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layer: str,
    shape: object,
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state",
        monkeypatch,
        session_id=f"shape-{layer}-{type(shape).__name__}",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if layer == "state":
        stored: object = shape
    elif layer == "receipt":
        state["receipt"] = shape
        stored = state
    else:
        state["receipt"]["setup_contract"] = shape
        unsigned_receipt = dict(state["receipt"])
        unsigned_receipt.pop("receipt_integrity_digest")
        state["receipt"]["receipt_integrity_digest"] = digest(unsigned_receipt)
        stored = state
    state_path.write_text(json.dumps(stored), encoding="utf-8")

    recovery_read = _pretool(base, "Read")
    assert "permissionDecision" not in recovery_read["hookSpecificOutput"]
    assert (
        "recovery-only read" in recovery_read["hookSpecificOutput"]["additionalContext"]
    )
    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "invalid startup state"
        in denied["hookSpecificOutput"]["permissionDecisionReason"]
    )


@pytest.mark.parametrize("target", ["folder", "driver"])
@pytest.mark.parametrize(("case", "malformed"), MALFORMED_DIGEST_CASES)
def test_malformed_binding_digests_deny_mutation_after_public_rehash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    case: str,
    malformed: object,
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id=f"malformed-{target}-{case}"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    if target == "folder":
        binding = receipt["setup_contract"]["required_skills"]["senior-harness"]
        key = "folder_digest"
    else:
        binding = receipt
        key = "driver_digest"
    if case == "missing":
        binding.pop(key)
    else:
        binding[key] = malformed
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "digest is missing or malformed"
        in denied["hookSpecificOutput"]["permissionDecisionReason"]
    )


@pytest.mark.parametrize(("case", "expected_error"), MALFORMED_SKILL_CASES)
def test_malformed_or_unavailable_skill_bindings_deny_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_error: str,
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id=f"binding-{case}"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    skills = receipt["setup_contract"]["required_skills"]
    if case == "skills-list":
        receipt["setup_contract"]["required_skills"] = []
    else:
        _malform_skill_binding(skills, case, tmp_path)
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert expected_error in denied["hookSpecificOutput"]["permissionDecisionReason"]

    recovery_read = _pretool(base, "Read")
    assert "permissionDecision" not in recovery_read["hookSpecificOutput"]
    assert (
        "recovery-only read" in recovery_read["hookSpecificOutput"]["additionalContext"]
    )


def test_invalid_utf8_bound_skill_enters_recovery_or_deny_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id="invalid-utf8-skill"
    )
    invalid_skill = tmp_path / "invalid-senior-harness"
    invalid_skill.mkdir()
    (invalid_skill / "SKILL.md").write_bytes(
        b"---\nname: senior-harness\n---\ninvalid utf-8: \xff\n"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    binding = receipt["setup_contract"]["required_skills"]["senior-harness"]
    binding["path"] = str(invalid_skill)
    binding["folder_digest"] = setup_driver_module._folder_digest(invalid_skill)
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    recovery_read = _pretool(base, "Read")
    read_output = recovery_read["hookSpecificOutput"]
    assert "permissionDecision" not in read_output
    assert "recovery-only read" in read_output["additionalContext"]
    assert "grants no mutation" in read_output["additionalContext"]
    assert (
        "bound skill is unavailable or invalid: senior-harness"
        in read_output["additionalContext"]
    )

    denied = _pretool(base, "Write")
    deny_output = denied["hookSpecificOutput"]
    assert deny_output["permissionDecision"] == "deny"
    assert (
        "bound skill is unavailable or invalid: senior-harness"
        in deny_output["permissionDecisionReason"]
    )
