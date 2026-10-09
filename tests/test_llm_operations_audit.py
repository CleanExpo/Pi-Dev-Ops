"""Dependency-free security and evidence checks, also collectable by pytest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import llm_operations_audit as doctor


class OperationsAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home, self.project = self.root / "home", self.root / "project"
        self.home.mkdir()
        self.project.mkdir()

    def put(self, root, relative, text):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def audit(self, **kwargs):
        return doctor.audit(self.home, [self.project], probe_clis=False, **kwargs)

    def test_unicode_size_hash_estimate(self):
        text = "# Café 🤖\n" * 3
        path = self.put(self.project, "AGENTS.md", text)
        row = next(row for row in self.audit()["instructions"] if row["path"] == str(path))
        self.assertEqual(row["bytes"], len(text.encode()))
        self.assertEqual(row["characters"], len(text))
        self.assertGreater(row["bytes"], row["characters"])
        self.assertEqual(row["sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(row["estimated_tokens_chars_div_4"], (len(text) + 3) // 4)
        self.assertNotIn(text, json.dumps(row))

    def test_config_only_model_values_no_secrets(self):
        sentinel = "sk-test-secret-fixture"
        self.put(self.home, ".codex/config.toml", f'model = "gpt-5.5"\nmodel_reasoning_effort = "high"\napi_key = "{sentinel}"\nbase_url = "https://private.example"\n')
        self.put(self.project, ".claude/settings.json", json.dumps({"model": "sonnet", "env": {"ANTHROPIC_MODEL": "claude-opus-4-7", "API_KEY": sentinel}}))
        self.put(self.home, ".codex/auth.json", "NEVER_READ_AUTH")
        original = Path.open
        def guarded_open(path, *args, **kwargs):
            self.assertNotEqual(path.name, "auth.json")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", guarded_open):
            report = self.audit()
        rendered = json.dumps(report)
        for value in (sentinel, "NEVER_READ_AUTH", "private.example", "api_key"):
            self.assertNotIn(value, rendered)
        self.assertTrue(any(row["allowed_values"].get("model") == "sonnet" for row in report["model_configs"]))
        self.assertTrue(any(row["allowed_values"].get("model_reasoning_effort") == "high" for row in report["model_configs"]))

    def test_untrusted_model_values(self):
        for value in ("sk-test-leak", "gpt-5.5 Bearer leak", "../auth.json", {"token": "leak"}, "claude-sk-secret", ["high"]):
            with self.subTest(value=value):
                self.put(self.home, ".claude/settings.json", json.dumps({"model": value}))
                row = next(row for row in self.audit()["model_configs"] if row["path"].endswith("/home/.claude/settings.json"))
                self.assertEqual(row["allowed_values"], {})

    def test_missing_malformed_config(self):
        self.put(self.home, ".codex/config.toml", 'model = "bad\n')
        self.put(self.project, ".claude/settings.json", "[]")
        self.assertTrue({"missing", "malformed_config"} <= {row["status"] for row in self.audit()["model_configs"]})

    def test_symlink_alias_and_source_identity(self):
        root = self.project / "skills"
        skill = self.put(root, "one/SKILL.md", "---\nname: one\ndescription: Does one thing.\n---\n")
        (root / "alias").symlink_to(skill.parent, target_is_directory=True)
        catalog = self.audit()["skill_catalog"]
        self.assertEqual(catalog["unique_skills"], 1)
        self.assertEqual(len(catalog["duplicate_aliases"]), 1)
        self.assertEqual(catalog["skills"][0]["source_path"], str(skill))
        self.assertEqual(catalog["rough_catalog_characters"], len("oneDoes one thing."))

    def test_symlink_cycle_is_bounded(self):
        root = self.project / "skills"
        self.put(root, "one/SKILL.md", "---\nname: one\ndescription: Fine.\n---\n")
        (root / "one/back").symlink_to(root, target_is_directory=True)
        catalog = self.audit()["skill_catalog"]
        self.assertEqual(catalog["unique_skills"], 1)
        self.assertLess(catalog["entries_examined"], 10)

    def test_outside_symlink_not_read(self):
        outside = self.put(self.root, "outside/SKILL.md", "SECRET_OUTSIDE_CONTENT")
        root = self.project / "skills"
        root.mkdir()
        (root / "escape").symlink_to(outside.parent, target_is_directory=True)
        report = self.audit()
        self.assertNotIn("SECRET_OUTSIDE_CONTENT", json.dumps(report))
        self.assertEqual(report["skill_catalog"]["unique_skills"], 0)
        self.assertTrue(any(row["status"] == "excluded_path" for row in report["skill_catalog"]["issues"]))

    def test_symlink_to_denied_target_never_opened(self):
        targets = [self.put(self.home, "auth.json", "SECRET_AUTH_TARGET"), self.put(self.home, ".env-dir/private.md", "SECRET_ENV_TARGET")]
        original = Path.open
        for index, target in enumerate(targets):
            with self.subTest(target=target):
                link = self.home / f"safe-{index}.md"
                link.symlink_to(target)
                def guarded_open(path, *args, **kwargs):
                    self.assertNotEqual(path.resolve(), target.resolve())
                    return original(path, *args, **kwargs)
                with patch.object(Path, "open", guarded_open):
                    text, status = doctor.read_bounded(link, [self.home.resolve()])
                self.assertIsNone(text)
                self.assertEqual(status, "excluded_path")

    def test_metadata_errors_and_description_not_emitted(self):
        root = self.project / "skills"
        self.put(root, "one/SKILL.md", "---\nname: one\ndescription: Bearer SECRET_DESCRIPTION\n---\n")
        self.put(root, "bad/SKILL.md", "---\nname: invalid name\ndescription: Fine.\n---\n")
        self.put(root, "malformed/SKILL.md", "---\nname: malformed\n")
        catalog = self.audit()["skill_catalog"]
        self.assertNotIn("SECRET_DESCRIPTION", json.dumps(catalog))
        self.assertEqual({row["metadata_status"] for row in catalog["skills"]}, {"ok", "missing_or_invalid_metadata", "malformed_frontmatter"})

    def test_broken_reference_sensitive_path_excluded(self):
        root = self.project / "skills"
        self.put(root, "one/SKILL.md", "---\nname: one\ndescription: Fine.\n---\n[missing](../missing/SKILL.md)\n`../../.env/SKILL.md`\n")
        self.put(root, "sk-hidden-secret/SKILL.md", "NEVER_READ_SENSITIVE_PATH")
        catalog = self.audit()["skill_catalog"]
        self.assertTrue({"broken_skill_reference", "excluded_skill_reference"} <= {row["status"] for row in catalog["issues"]})
        self.assertNotIn("sk-hidden-secret", json.dumps(catalog))
        self.assertNotIn("NEVER_READ_SENSITIVE_PATH", json.dumps(catalog))

    def test_large_file_and_catalog_limit(self):
        self.put(self.project, "AGENTS.md", "a" * 81)
        for number in range(10):
            self.put(self.project, f"skills/item-{number}/SKILL.md", "---\nname: one\ndescription: Fine.\n---\n")
        with patch.object(doctor, "MAX_BYTES", 80):
            report = self.audit(max_entries=3)
        self.assertTrue(report["skill_catalog"]["truncated"])
        self.assertLessEqual(report["skill_catalog"]["entries_examined"], 3)
        row = next(row for row in report["instructions"] if row["path"].endswith("/project/AGENTS.md"))
        self.assertEqual(row["status"], "over_byte_limit")

    def test_source_is_not_runtime_or_access(self):
        self.put(self.project, doctor.DEFAULT_ROUTE_FILES[0], 'MODEL = "claude-opus-5"\nTOKEN = "sk-secret"\nWORKER = "claude-1"\nPREFIX = "claude-opus-"\n')
        rows = self.audit()["source_routes"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["availability"], "unknown")
        self.assertEqual(rows[0]["evidence"], "source_literal_only")
        self.assertNotIn("sk-secret", json.dumps(rows))

    def test_instruction_import_sources_are_bounded(self):
        self.put(self.home, ".claude/CLAUDE.md", "@./shared.md\n@./.env\n")
        imported = self.put(self.home, ".claude/shared.md", "évidence\n@./CLAUDE.md\n")
        rows = self.audit()["instructions"]
        row = next(row for row in rows if row.get("source_path") == str(imported))
        self.assertEqual(row["imported_by"], str(self.home / ".claude/CLAUDE.md"))
        self.assertTrue(any(row["status"] == "excluded_path" for row in rows))
        self.assertLess(len(rows), 10)

    def test_runner_status_never_overstates_health(self):
        runner = self.project / "runner"
        cases = [("running", "absent", "recorded_active_but_pid_absent"), ("running", "present_identity_unverified", "unknown"), ("stopped", "present_identity_unverified", "recorded_stopped_process_unverified"), ("paused", "absent", "recorded_stopped_pid_absent"), ("running", "unknown", "unknown")]
        for recorded, process, expected in cases:
            with self.subTest(recorded=recorded, process=process):
                self.put(runner, "state.json", json.dumps({"state": recorded, "pid": 99999, "token": "SECRET_RECEIPT"}))
                with patch.object(doctor, "pid_state", return_value=process):
                    rows = self.audit(runner_roots=[runner])["runner_receipts"]
                self.assertEqual(rows[0]["runtime"], expected)
                self.assertNotIn("SECRET_RECEIPT", json.dumps(rows))

    def test_invalid_pid_is_unknown(self):
        self.assertTrue(all(doctor.pid_state(value) == "unknown" for value in (True, False, "12", 0, -8, None)))

    def executable(self, body):
        path = self.root / "fake-cli"
        path.write_text(f"#!{sys.executable}\n{body}\n")
        path.chmod(0o700)
        return str(path)

    def test_probe_deadline_and_no_raw_output(self):
        path = self.executable('import time\nprint("Bearer SECRET_STDOUT", flush=True)\ntime.sleep(5)')
        started = time.monotonic()
        result = doctor.bounded_version(path, timeout=0.15)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(result, {"status": "timeout", "version": None})

    def test_probe_output_cap(self):
        real_popen = doctor.subprocess.Popen
        def fixture_popen(argv, **kwargs):
            self.assertEqual(argv, ["fixture-cli", "--version"])
            return real_popen([sys.executable, "-c", 'import os; os.write(1, b"x" * 1024)'], **kwargs)
        with patch.object(doctor.subprocess, "Popen", fixture_popen):
            self.assertEqual(doctor.bounded_version("fixture-cli", timeout=10, output_limit=100)["status"], "output_limit")

    def test_probe_numeric_version_only(self):
        path = self.executable('print("Claude Code 2.1.295 Bearer SECRET")')
        self.assertEqual(doctor.bounded_version(path, timeout=2), {"status": "ok", "version": "2.1.295"})

    def test_nonmutating_inventory(self):
        self.put(self.project, "AGENTS.md", "Original")
        self.put(self.home, ".codex/config.toml", 'model = "gpt-5.5"\n')
        def snapshot():
            return {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for root in (self.home, self.project) for path in root.rglob("*") if path.is_file()}
        before = snapshot()
        self.audit()
        self.assertEqual(before, snapshot())

    def test_report_new_external_json_only(self):
        external = self.root / "external"
        external.mkdir()
        output = external / "receipt.json"
        doctor.write_report(output, {"safe": True}, [], external)
        self.assertEqual(json.loads(output.read_text()), {"safe": True})
        for target in (output, self.root / "internal.json", external / ".env.json"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                doctor.write_report(target, {}, [], external)

    def test_report_output_symlink_not_followed(self):
        external = self.root / "external"
        external.mkdir()
        outside = self.root / "original.json"
        outside.write_text("original")
        link = external / "receipt.json"
        link.symlink_to(outside)
        with self.assertRaises(ValueError):
            doctor.write_report(link, {}, [], external)
        self.assertEqual(outside.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
