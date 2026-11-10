#!/usr/bin/env python3
"""Tests for capability_passport.py. Stdlib only; every test builds a throwaway skills tree.

The six refusals the founder brief names each have their own test, and each of those tests
is paired with a targeted sabotage in skills/enforcement-loop/install/positive_control.py,
so CI proves every one of them can go red. A clean skill that must be ALLOWED is the positive
control here: without it, a bug that refuses everything would pass all six.

    python3 skills/skill-watch/tests/test_capability_passport.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("capability_passport", HERE.parent / "scripts" / "capability_passport.py")
cp = importlib.util.module_from_spec(SPEC)
sys.modules["capability_passport"] = cp
SPEC.loader.exec_module(cp)
SCHEMA = json.loads((HERE.parent / "capability-passport.schema.json").read_text())
SHA = "b" * 40


def skill(root: Path, folder: str, name: str, description: str, extra: str = "") -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n# {name}\n")
    return d / "SKILL.md"


class Fixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.skills = base / "skills"
        self.vault = base / "skill-vault"
        self.state = base / "state"
        skill(self.skills, "clean", "clean", "Reads files and reports.", "allowed-tools: Read, Grep\ncapabilities: summarise a file\n")
        skill(self.skills, "shell", "shell", "Runs anything.", "capabilities: run a build\n")
        skill(self.skills, "modelled", "modelled", "Needs a named model.",
              "allowed-tools: Read\nmodel: claude-opus-test\ncapabilities: think hard\n")
        skill(self.skills, "retired", "retired", "Names a retired model.", "allowed-tools: Read\nmodel: fixture-retired-model\n")
        skill(self.skills, "lane", "lane", "Names an API-key lane.", "allowed-tools: Read\nmodel: meta-llama/llama-3.3-70b-instruct\n")
        skill(self.skills, "owner-a", "owner-a", "First claimant.", "allowed-tools: Read\nowner: alpha\ncapabilities: ship a release\n")
        skill(self.skills, "owner-b", "owner-b", "Second claimant.", "allowed-tools: Read\nowner: beta\ncapabilities: ship a release\n")
        skill(self.skills, "npmtool", "npmtool", "Installed from npm, reviewed.", "allowed-tools: Read\n")
        skill(self.skills, "npmraw", "npmraw", "Installed from npm with no pinned version.", "allowed-tools: Read\n")
        skill(self.vault / "ext", "reviewed-ext", "reviewed-ext", "Outside skill, reviewed.", "allowed-tools: Read\n")
        skill(self.vault / "rawext", "raw-ext", "raw-ext", "Outside skill, review left blank.", "allowed-tools: Read\n")
        skill(self.vault / "stray", "stray-ext", "stray-ext", "Outside skill with no registry entry.", "allowed-tools: Read\n")
        (self.skills / "skill-watch").mkdir()
        (self.skills / "skill-watch" / "external-skills.json").write_text(json.dumps({"skills": [
            {"name": "ext", "repo": "https://example.invalid/ext", "pinned_sha": SHA, "review": "read 31/10/2026", "vault": True},
            {"name": "rawext", "repo": "https://example.invalid/raw", "pinned_sha": SHA, "review": "", "vault": True},
            {"name": "npmtool", "npm": "npmtool", "pinned_version": "1.2.3", "review": "read 31/10/2026"},
            {"name": "npmraw", "npm": "npmraw", "pinned_version": "", "review": "read 31/10/2026"},
        ]}))
        (self.skills / "HOMES.json").write_text(json.dumps({"homes": {"clean": "library", "shell": "library"}}))
        (self.skills / "index.md").write_text(
            "| Intent / trigger phrase | Canonical skill | Notes |\n|---|---|---|\n"
            '| "tidy the notes" / "summarise a file" | `clean` | x |\n\n')
        self.retired = base / "retired-models.txt"
        self.retired.write_text("fixture-retired-model  # retired 21/07/2025 source=https://example.invalid\n")
        self.roots = cp.Roots(skills=self.skills, vault=self.vault, state=self.state, retired=self.retired)

    def generate(self) -> dict:
        return cp.generate(self.roots)

    def activate(self, doc: dict, name: str, **kw) -> dict:
        kw.setdefault("available_models", ["claude-opus-test", "sonnet"])
        return cp.activate(self.roots, doc, name, **kw)

    def close(self) -> None:
        self._tmp.cleanup()


class PassportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def passport(self, doc: dict, name: str) -> dict:
        return next(p for p in doc["passports"] if p["name"] == name)

    # ---- schema and identity ------------------------------------------------------

    def test_every_generated_passport_validates_and_pins_the_source_hash(self):
        doc = self.f.generate()
        self.assertEqual(len(doc["passports"]), 12)
        for p in doc["passports"]:
            self.assertEqual(cp.validate(p, SCHEMA), [], p["name"])
        clean = self.passport(doc, "clean")
        raw = (self.f.skills / "clean" / "SKILL.md").read_bytes()
        self.assertEqual(clean["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIn("summarise a file", clean["capabilities"])
        self.assertIn("tidy the notes", clean["capabilities"])  # router phrase, not frontmatter
        self.assertEqual(clean["owner"], "library")  # HOMES.json, no frontmatter owner

    def test_schema_rejects_a_tampered_passport_and_unknown_keywords(self):
        p = dict(self.passport(self.f.generate(), "clean"))
        p["risk"] = {"level": "none", "reasons": []}
        p["extra"] = 1
        errors = cp.validate(p, SCHEMA)
        self.assertTrue(any("risk.level" in e for e in errors), errors)
        self.assertTrue(any("extra" in e for e in errors), errors)
        del p["owner"]
        self.assertTrue(any("owner" in e for e in cp.validate(p, SCHEMA)))
        with self.assertRaises(cp.SchemaError):
            cp.validate({}, {"type": "object", "if": {}})

    def test_activation_refuses_a_passport_that_fails_the_schema(self):
        doc = self.f.generate()
        self.passport(doc, "clean")["risk"]["level"] = "none"
        r = self.f.activate(doc, "clean")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("SCHEMA_INVALID", r["codes"])

    # ---- positive control ---------------------------------------------------------

    def test_clean_skill_is_allowed_and_the_receipt_is_simulated(self):
        doc = self.f.generate()
        before = sorted(str(p) for p in self.f.skills.rglob("*"))
        r = self.f.activate(doc, "clean", capability="summarise a file", max_risk="low")
        self.assertEqual(r["decision"], "ALLOW", r)
        self.assertEqual(r["codes"], [])
        self.assertIs(r["simulated"], True)
        self.assertEqual(r["passport_sha256"], cp.canonical_sha256(self.passport(doc, "clean")))
        self.assertEqual(before, sorted(str(p) for p in self.f.skills.rglob("*")), "activation changed the tree")

    # ---- the six required refusals ------------------------------------------------

    def test_fake_pass_record_is_rejected(self):
        cmd = [sys.executable, "-c", "print('ok')"]
        good = cp.record(self.f.roots, "clean", cmd)
        self.assertEqual(good["verdict"], "PASS")
        self.assertEqual(self.passport(self.f.generate(), "clean")["tests"]["status"], "PASS")
        # A hand-written PASS whose exit code says the command failed.
        forged = dict(good, exit_code=1)
        with (self.f.state / "test-records.jsonl").open("a") as fh:
            fh.write(json.dumps(forged) + "\n")
        doc = self.f.generate()
        self.assertEqual(self.passport(doc, "clean")["tests"]["status"], "REJECTED")
        r = self.f.activate(doc, "clean")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("FAKE_PASS", r["codes"])

    def test_pass_record_whose_output_log_was_altered_is_rejected(self):
        good = cp.record(self.f.roots, "clean", [sys.executable, "-c", "print('ok')"])
        Path(good["output_path"]).write_text("edited after the fact\n")
        doc = self.f.generate()
        self.assertEqual(self.passport(doc, "clean")["tests"]["status"], "REJECTED")
        self.assertIn("FAKE_PASS", self.f.activate(doc, "clean")["codes"])

    def test_stale_sha_refuses_activation(self):
        doc = self.f.generate()
        path = self.f.skills / "clean" / "SKILL.md"
        path.write_text(path.read_text() + "\nA line added after the passport was generated.\n")
        r = self.f.activate(doc, "clean")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("STALE_SHA", r["codes"])
        # A test record bound to the old hash no longer counts as a pass.
        cp.record(self.f.roots, "clean", [sys.executable, "-c", "pass"])
        path.write_text(path.read_text() + "\nAnother edit.\n")
        self.assertEqual(self.passport(self.f.generate(), "clean")["tests"]["status"], "STALE")

    def test_unreviewed_outside_skill_is_refused(self):
        doc = self.f.generate()
        self.assertIs(self.passport(doc, "reviewed-ext")["trust"]["reviewed"], True)
        self.assertEqual(self.f.activate(doc, "reviewed-ext")["decision"], "ALLOW")
        self.assertIs(self.passport(doc, "npmtool")["trust"]["reviewed"], True)  # npm pin, not a git SHA
        for name in ("raw-ext", "stray-ext", "npmraw"):
            p = self.passport(doc, name)
            self.assertIs(p["trust"]["reviewed"], False, name)
            r = self.f.activate(doc, name)
            self.assertEqual(r["decision"], "REFUSE", name)
            self.assertIn("UNREVIEWED", r["codes"], name)

    def test_conflicting_owners_are_detected_and_refused(self):
        doc = self.f.generate()
        self.assertIn({"capability": "ship a release", "owners": ["alpha", "beta"]}, doc["conflicts"])
        self.assertEqual(self.passport(doc, "owner-a")["conflicts"][0]["owners"], ["alpha", "beta"])
        r = self.f.activate(doc, "owner-a", capability="ship a release")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("CONFLICTING_OWNERS", r["codes"])

    def test_missing_capability_is_refused(self):
        doc = self.f.generate()
        r = self.f.activate(doc, "clean", capability="deploy to production")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("MISSING_CAPABILITY", r["codes"])
        self.assertIn("NO_PASSPORT", self.f.activate(doc, "never-generated")["codes"])

    def test_model_unavailability_is_refused_never_substituted(self):
        doc = self.f.generate()
        self.assertEqual(self.f.activate(doc, "modelled")["decision"], "ALLOW")
        r = self.f.activate(doc, "modelled", available_models=["sonnet"])
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("MODEL_UNAVAILABLE", r["codes"])
        self.assertIsNone(r["model"]["substitute"])
        self.assertIn("MODEL_UNKNOWN", self.f.activate(doc, "modelled", available_models=None)["codes"])
        self.assertIn("MODEL_RETIRED", self.f.activate(doc, "retired", available_models=["fixture-retired-model"])["codes"])
        lane = self.f.activate(doc, "lane", available_models=["meta-llama/llama-3.3-70b-instruct"])
        self.assertIn("API_KEY_LANE", lane["codes"])

    # ---- risk filter ----------------------------------------------------------------

    def test_risk_filter_blocks_skills_above_the_limit(self):
        doc = self.f.generate()
        shell = self.passport(doc, "shell")
        self.assertEqual(shell["risk"]["level"], "high")  # no allowed-tools: inherits every tool
        r = self.f.activate(doc, "shell", capability="run a build", max_risk="medium")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("RISK_ABOVE_LIMIT", r["codes"])
        self.assertEqual(self.f.activate(doc, "shell", capability="run a build", max_risk="high")["decision"], "ALLOW")
        self.assertEqual(cp.risk_for(["Read", "Bash(git status *)"], True)[0], "medium")
        self.assertEqual(cp.risk_for(["Read", "Bash"], True)[0], "high")

    def test_require_tested_refuses_an_untested_skill(self):
        doc = self.f.generate()
        self.assertIn("UNTESTED", self.f.activate(doc, "clean", require_tested=True)["codes"])

    # ---- review findings of 31/10/2026 (Codex, fa5a75fa), one guard each --------------

    def test_indentless_yaml_tool_list_is_read_not_dropped(self):
        skill(self.f.skills, "listed", "listed", "Tools as an indentless YAML list.", "allowed-tools:\n- Read\n- Bash\n")
        p = self.passport(self.f.generate(), "listed")
        self.assertEqual(p["tools"]["list"], ["Read", "Bash"])
        self.assertEqual(p["risk"]["level"], "high")

    def test_a_newer_failed_run_overrides_an_older_pass(self):
        cp.record(self.f.roots, "clean", [sys.executable, "-c", "pass"])
        cp.record(self.f.roots, "clean", [sys.executable, "-c", "raise SystemExit(7)"])
        doc = self.f.generate()
        self.assertEqual(self.passport(doc, "clean")["tests"]["status"], "FAIL")
        self.assertIn("UNTESTED", self.f.activate(doc, "clean", require_tested=True)["codes"])

    def test_symlinked_skills_get_passports_and_vault_links_keep_vault_trust(self):
        outside = Path(self.f._tmp.name) / "vendored" / "linked"
        skill(outside.parent, "linked", "linked", "A vendored skill reached through a symlink.", "allowed-tools: Read\n")
        (self.f.skills / "linked").symlink_to(outside, target_is_directory=True)
        (self.f.skills / "raw-ext").symlink_to(self.f.vault / "rawext" / "raw-ext", target_is_directory=True)
        doc = self.f.generate()
        self.assertEqual(self.passport(doc, "linked")["origin"], "local")
        raw = self.passport(doc, "raw-ext")
        self.assertEqual(raw["origin"], "vault")  # a shelf checkout must not launder vault trust
        self.assertIs(raw["trust"]["reviewed"], False)
        self.assertEqual(sum(p["name"] == "raw-ext" for p in doc["passports"]), 1)

    def test_unsupported_keyword_in_an_unreached_subschema_still_raises(self):
        with self.assertRaises(cp.SchemaError):
            cp.validate([], {"type": "array", "items": {"minItems": 1}})

    def test_malformed_stored_passport_gets_a_refusal_receipt_not_a_crash(self):
        doc = self.f.generate()
        del self.passport(doc, "clean")["source"]
        r = self.f.activate(doc, "clean")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("SCHEMA_INVALID", r["codes"])

    def test_review_withdrawn_after_generation_is_refused(self):
        doc = self.f.generate()
        reg = self.f.skills / "skill-watch" / "external-skills.json"
        data = json.loads(reg.read_text())
        data["skills"][0]["review"] = ""
        reg.write_text(json.dumps(data))
        r = self.f.activate(doc, "reviewed-ext")
        self.assertEqual(r["decision"], "REFUSE")
        self.assertIn("UNREVIEWED", r["codes"])


if __name__ == "__main__":
    unittest.main()
