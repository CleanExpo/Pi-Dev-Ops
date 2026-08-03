"""Red-first proof for config_loader: one paired observation per accessor.

Each accessor is observed BOTH ways in the same run:
  - file ABSENT  -> raises ConfigMissingError, or resolves to the in-code spec
  - file PRESENT -> normal behaviour

An accessor never observed failing is not covered. These tests exist so that a missed
consumer in commit 1b announces itself instead of returning an empty value.

Absence is simulated by pointing the module's path constants at an empty directory —
the real files are never moved or deleted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.server import config_loader as cl


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    return tmp_path / "nowhere"


# ── SPECIFICATION: absence is CORRECT, not degraded ──────────────────────────
def test_harness_config_absent_resolves_to_spec(monkeypatch, empty_dir):
    monkeypatch.setattr(cl, "CONFIG_YAML", empty_dir / "config.yaml")
    cfg = cl.harness_config(refresh=True)
    assert cfg["agents"]["planner"]["model"] == "opus"
    assert cfg["agents"]["orchestrator"]["model"] == "opus"
    assert cfg["agents"]["adversary"]["model"] == "opus"
    assert cfg["agents"]["monitor"]["model"] == "haiku"


def test_agent_models_absent_is_never_all_sonnet(monkeypatch, empty_dir):
    """The exact regression: a missing file must not collapse every role to sonnet."""
    monkeypatch.setattr(cl, "CONFIG_YAML", empty_dir / "config.yaml")
    models = {r: c["model"] for r, c in cl.agent_models(refresh=True).items()}
    assert models != {r: "sonnet" for r in models}
    assert models["planner"] == "opus"
    assert models["monitor"] == "haiku"


def test_harness_config_present_overrides_spec(monkeypatch, tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"agents": {"planner": {"model": "haiku"}}}), encoding="utf-8")
    monkeypatch.setattr(cl, "CONFIG_YAML", p)
    cfg = cl.harness_config(refresh=True)
    assert cfg["agents"]["planner"]["model"] == "haiku"          # override wins
    assert cfg["agents"]["orchestrator"]["model"] == "opus"      # spec survives merge


def test_harness_config_malformed_still_raises(monkeypatch, tmp_path):
    """Unreadable is not the same as absent — a corrupt file must not silently become spec."""
    p = tmp_path / "config.yaml"
    p.write_text("agents: [unclosed\n", encoding="utf-8")
    monkeypatch.setattr(cl, "CONFIG_YAML", p)
    with pytest.raises(cl.ConfigMissingError):
        cl.harness_config(refresh=True)


# ── INSTANCE DATA: absence RAISES ────────────────────────────────────────────
@pytest.mark.parametrize(
    "const,accessor,payload,dumper",
    [
        ("PROJECTS_JSON", "projects", {"projects": []}, json.dumps),
        ("CRON_TRIGGERS_JSON", "cron_triggers", [], json.dumps),
        ("CONTENT_MANIFEST_JSON", "content_manifest", {"x": 1}, json.dumps),
        ("PROVISIONED_TOOLS_YAML", "provisioned_tools", {"provisioned": []}, yaml.safe_dump),
    ],
)
def test_instance_accessor_paired(monkeypatch, tmp_path, const, accessor, payload, dumper):
    fn = getattr(cl, accessor)

    # RED: absent -> raises
    monkeypatch.setattr(cl, const, tmp_path / "nowhere" / "f")
    with pytest.raises(cl.ConfigMissingError):
        fn()

    # GREEN: present -> normal behaviour (paired positive; without it the raise is uninterpretable)
    p = tmp_path / "f"
    p.write_text(dumper(payload), encoding="utf-8")
    monkeypatch.setattr(cl, const, p)
    assert fn() == payload


# ── SPLIT FILE: spec defaults, external identifiers do not ───────────────────
def _margot_payload() -> dict:
    return {
        "elevenlabs": {"voice_id": "vid"},
        "projects": {"a": 1},
        "canonical_wiki_page": "Wiki/Margot",
        "base_prompt": "hello",
    }


def test_margot_absent_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(cl, "MARGOT_IDENTITY_JSON", tmp_path / "nowhere.json")
    with pytest.raises(cl.ConfigMissingError):
        cl.margot_identity()


@pytest.mark.parametrize("key", cl.MARGOT_REQUIRED_KEYS)
def test_margot_missing_external_identifier_raises(monkeypatch, tmp_path, key):
    """An external resource id is never defaulted — being wrong about one is invisible."""
    data = _margot_payload()
    data.pop(key)
    p = tmp_path / "m.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(cl, "MARGOT_IDENTITY_JSON", p)
    with pytest.raises(cl.ConfigMissingError) as exc:
        cl.margot_identity()
    assert key in str(exc.value)


def test_margot_present_defaults_spec_keys(monkeypatch, tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_margot_payload()), encoding="utf-8")
    monkeypatch.setattr(cl, "MARGOT_IDENTITY_JSON", p)
    out = cl.margot_identity()
    assert out["base_prompt"] == "hello"      # from file
    assert out["safety_rules"] == []          # spec default, file omitted it
    assert out["elevenlabs"]["voice_id"] == "vid"


# ── STARTUP VALIDATOR ────────────────────────────────────────────────────────
def test_validate_startup_raises_and_names_every_missing_file(monkeypatch, tmp_path):
    for const, _ in [(c, n) for c, n in
                     [("PROJECTS_JSON", 1), ("CRON_TRIGGERS_JSON", 1),
                      ("CONTENT_MANIFEST_JSON", 1), ("PROVISIONED_TOOLS_YAML", 1),
                      ("MARGOT_IDENTITY_JSON", 1)]]:
        monkeypatch.setattr(cl, const, tmp_path / "nowhere" / const)
    monkeypatch.setattr(cl, "REQUIRED_AT_STARTUP", tuple(
        (getattr(cl, c), n) for c, n in [
            ("PROJECTS_JSON", "projects.json"),
            ("CRON_TRIGGERS_JSON", "cron-triggers.json"),
            ("CONTENT_MANIFEST_JSON", "content_manifest.json"),
            ("PROVISIONED_TOOLS_YAML", "provisioned-tools.yaml"),
            ("MARGOT_IDENTITY_JSON", "margot_identity.json"),
        ]))
    with pytest.raises(cl.ConfigMissingError) as exc:
        cl.validate_startup()
    for name in ("projects.json", "cron-triggers.json", "content_manifest.json",
                 "provisioned-tools.yaml", "margot_identity.json"):
        assert name in str(exc.value)


def test_validate_startup_passes_when_all_present():
    """Paired positive against the REAL repo files — proves the validator can also succeed."""
    cl.validate_startup()


def test_validate_startup_rejects_a_malformed_registry(monkeypatch, tmp_path):
    """Review #3 of #611: existence alone let malformed registry data through to consumers
    that all degrade softly by design. Startup must parse it, not just stat it."""
    bad = tmp_path / "notebooklm-registry.json"
    bad.write_text("{this is not json", encoding="utf-8")
    monkeypatch.setattr(cl, "NOTEBOOKLM_REGISTRY_JSON", bad)
    monkeypatch.setattr(cl, "REQUIRED_AT_STARTUP", ((bad, "notebooklm-registry.json"),))
    with pytest.raises(cl.ConfigMissingError, match="not valid JSON"):
        cl.validate_startup()


# ── BOARD GOVERNANCE CORPUS ──────────────────────────────────────────────────
# The corpus is a tracked directory the Dockerfile COPYs. Absence is a packaging
# error, so it belongs at boot — where someone is watching — rather than at 05:00
# UTC inside the unattended board-meeting cron, which is where the mandate gate
# would otherwise discover it.
def test_validate_startup_raises_when_board_corpus_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(cl, "BOARD_MEETINGS_DIR", tmp_path / "nowhere" / "board-meetings")
    with pytest.raises(cl.ConfigMissingError) as exc:
        cl.validate_startup()
    assert "board-meetings" in str(exc.value)


def test_validate_startup_raises_when_board_corpus_locks_nothing(monkeypatch, tmp_path):
    """Existence is not enough, exactly as for the NotebookLM registry.

    Markdown with no '## Conditions Locked' section yields an empty index, and an
    empty index is what makes the mandate gate approve everything. A corpus that
    parses to zero decisions is the same defect as an absent one.
    """
    corpus = tmp_path / "board-meetings"
    corpus.mkdir()
    (corpus / "notes.md").write_text("# Board notes\n\nNothing locked.\n", encoding="utf-8")
    monkeypatch.setattr(cl, "BOARD_MEETINGS_DIR", corpus)
    with pytest.raises(cl.ConfigMissingError):
        cl.validate_startup()
